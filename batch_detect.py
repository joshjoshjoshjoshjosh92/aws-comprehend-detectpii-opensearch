"""
Comprehend async batch job for large-scale PII detection.

50% cheaper than real-time API. Use for 10K+ documents.

Flow:
  1. Export unscanned docs from OpenSearch → S3
  2. Start Comprehend PII detection job
  3. Poll for completion
  4. Parse results and update OpenSearch
"""
import json
import time
import boto3
from config import REGION, OPENSEARCH_INDEX, COMPREHEND_LANGUAGE, PII_ENTITY_TYPES
from os_client import get_client

comprehend = boto3.client("comprehend", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)


def export_to_s3(bucket: str, prefix: str = "pii-batch-input/", max_docs: int = 10000) -> int:
    """Export unscanned docs from OpenSearch to S3 as one-doc-per-line format."""
    client = get_client()
    query = {"query": {"bool": {"must_not": {"exists": {"field": "pii_flag"}}}}}

    doc_count = 0
    batch_lines = []
    file_num = 0

    while doc_count < max_docs:
        resp = client.search(index=OPENSEARCH_INDEX, body={**query, "size": 100})
        hits = resp["hits"]["hits"]
        if not hits:
            break

        for hit in hits:
            text_fields = [v for v in hit["_source"].values() if isinstance(v, str) and len(v) > 20]
            combined = " ".join(text_fields)
            if combined:
                batch_lines.append(json.dumps({"id": hit["_id"], "text": combined[:4900]}))
                doc_count += 1

            if len(batch_lines) >= 1000:
                key = f"{prefix}batch_{file_num:04d}.jsonl"
                s3.put_object(Bucket=bucket, Key=key, Body="\n".join(batch_lines))
                print(f"  Wrote {key} ({len(batch_lines)} docs)")
                batch_lines = []
                file_num += 1

        # Mark these as in-progress so we don't re-export
        bulk_body = ""
        for hit in hits:
            action = json.dumps({"update": {"_index": OPENSEARCH_INDEX, "_id": hit["_id"]}})
            doc = json.dumps({"doc": {"pii_scan_status": "in_progress"}})
            bulk_body += action + "\n" + doc + "\n"
        client.bulk(body=bulk_body)

    # Flush remaining
    if batch_lines:
        key = f"{prefix}batch_{file_num:04d}.jsonl"
        s3.put_object(Bucket=bucket, Key=key, Body="\n".join(batch_lines))
        print(f"  Wrote {key} ({len(batch_lines)} docs)")

    print(f"Exported {doc_count} documents to s3://{bucket}/{prefix}")
    return doc_count


def start_job(bucket: str, input_prefix: str = "pii-batch-input/",
              output_prefix: str = "pii-batch-output/", role_arn: str = None) -> str:
    """Start a Comprehend PII detection batch job."""
    if not role_arn:
        raise ValueError("role_arn is required for Comprehend batch jobs")

    resp = comprehend.start_pii_entities_detection_job(
        InputDataConfig={
            "S3Uri": f"s3://{bucket}/{input_prefix}",
            "InputFormat": "ONE_DOC_PER_LINE",
        },
        OutputDataConfig={
            "S3Uri": f"s3://{bucket}/{output_prefix}",
        },
        Mode="ONLY_OFFSETS",
        LanguageCode=COMPREHEND_LANGUAGE,
        DataAccessRoleArn=role_arn,
        JobName=f"pii-detect-{int(time.time())}",
    )
    job_id = resp["JobId"]
    print(f"Started Comprehend batch job: {job_id}")
    return job_id


def wait_for_job(job_id: str, poll_interval: int = 30) -> dict:
    """Poll until job completes."""
    while True:
        resp = comprehend.describe_pii_entities_detection_job(JobId=job_id)
        status = resp["PiiEntitiesDetectionJobProperties"]["JobStatus"]
        print(f"  Job {job_id}: {status}")

        if status == "COMPLETED":
            return resp["PiiEntitiesDetectionJobProperties"]
        elif status in ("FAILED", "STOP_REQUESTED", "STOPPED"):
            raise RuntimeError(f"Job failed with status: {status}")

        time.sleep(poll_interval)


def import_results(bucket: str, output_prefix: str = "pii-batch-output/"):
    """Parse Comprehend batch output and update OpenSearch."""
    client = get_client()

    # List output files
    resp = s3.list_objects_v2(Bucket=bucket, Prefix=output_prefix)
    if "Contents" not in resp:
        print("No output files found.")
        return

    total_updated = 0
    for obj in resp["Contents"]:
        if not obj["Key"].endswith(".out"):
            continue

        data = s3.get_object(Bucket=bucket, Key=obj["Key"])
        bulk_body = ""

        for line in data["Body"].read().decode("utf-8").strip().split("\n"):
            result = json.loads(line)
            entities = [
                e for e in result.get("Entities", [])
                if e["Type"] in PII_ENTITY_TYPES and e["Score"] >= 0.7
            ]
            doc_id = result.get("File", "").replace(".jsonl", "")  # depends on output format

            update = {
                "pii_flag": len(entities) > 0,
                "pii_count": len(entities),
                "pii_types": list({e["Type"] for e in entities}),
                "pii_scanned_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "pii_scan_status": "complete",
            }

            action = json.dumps({"update": {"_index": OPENSEARCH_INDEX, "_id": doc_id}})
            doc = json.dumps({"doc": update})
            bulk_body += action + "\n" + doc + "\n"
            total_updated += 1

            if total_updated % 500 == 0:
                client.bulk(body=bulk_body)
                bulk_body = ""

        if bulk_body:
            client.bulk(body=bulk_body)

    print(f"Updated {total_updated} documents from batch results.")


def run_batch(bucket: str, role_arn: str, max_docs: int = 10000):
    """Full batch pipeline: export → detect → import."""
    print("=== Step 1: Export to S3 ===")
    count = export_to_s3(bucket, max_docs=max_docs)
    if count == 0:
        print("Nothing to process.")
        return

    print("\n=== Step 2: Start Comprehend Job ===")
    job_id = start_job(bucket, role_arn=role_arn)

    print("\n=== Step 3: Wait for Completion ===")
    job_props = wait_for_job(job_id)

    print("\n=== Step 4: Import Results ===")
    output_uri = job_props["OutputDataConfig"]["S3Uri"]
    output_prefix = output_uri.replace(f"s3://{bucket}/", "")
    import_results(bucket, output_prefix)

    print("\n=== Done ===")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run Comprehend batch PII detection")
    parser.add_argument("--bucket", required=True, help="S3 bucket for input/output")
    parser.add_argument("--role-arn", required=True, help="IAM role ARN for Comprehend data access")
    parser.add_argument("--max-docs", type=int, default=10000)
    args = parser.parse_args()
    run_batch(args.bucket, args.role_arn, args.max_docs)
