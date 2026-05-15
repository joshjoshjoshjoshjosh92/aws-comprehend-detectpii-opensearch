"""
Lambda handler for serverless PII detection.

Triggers:
  - S3 event: new document lands → detect PII → index to OpenSearch
  - EventBridge schedule: scan unscanned docs in OpenSearch
  - Direct invoke: process a single document payload
"""
import json
import os
import time
import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth

# Config from environment
REGION = os.environ.get("AWS_REGION", "us-east-1")
OPENSEARCH_ENDPOINT = os.environ["OPENSEARCH_ENDPOINT"]
OPENSEARCH_INDEX = os.environ.get("OPENSEARCH_INDEX", "pii-test")
COMPREHEND_LANGUAGE = os.environ.get("COMPREHEND_LANGUAGE", "en")
PII_HANDLING_MODE = os.environ.get("PII_HANDLING_MODE", "REDACT")
PII_CONFIDENCE_THRESHOLD = float(os.environ.get("PII_CONFIDENCE_THRESHOLD", "0.7"))
PII_ENTITY_TYPES = os.environ.get("PII_ENTITY_TYPES", "NAME,SSN,CREDIT_DEBIT_NUMBER,EMAIL,PHONE,ADDRESS,DATE_TIME,BANK_ACCOUNT_NUMBER").split(",")
BATCH_SIZE = int(os.environ.get("SCAN_BATCH_SIZE", "25"))

# Cached clients
comprehend = boto3.client("comprehend", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)


def get_os_client():
    creds = boto3.Session().get_credentials()
    auth = AWSV4SignerAuth(creds, REGION, "es")
    return OpenSearch(
        hosts=[{"host": OPENSEARCH_ENDPOINT, "port": 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
    )


def contains_pii(text: str) -> bool:
    text = text[:99_000]
    resp = comprehend.contains_pii_entities(Text=text, LanguageCode=COMPREHEND_LANGUAGE)
    return any(
        label["Score"] >= PII_CONFIDENCE_THRESHOLD and label["Name"] in PII_ENTITY_TYPES
        for label in resp.get("Labels", [])
    )


def detect_pii(text: str) -> list:
    text = text[:99_000]
    resp = comprehend.detect_pii_entities(Text=text, LanguageCode=COMPREHEND_LANGUAGE)
    return [
        e for e in resp.get("Entities", [])
        if e["Type"] in PII_ENTITY_TYPES and e["Score"] >= PII_CONFIDENCE_THRESHOLD
    ]


def redact_text(text: str, entities: list) -> str:
    for ent in sorted(entities, key=lambda e: e["BeginOffset"], reverse=True):
        text = text[:ent["BeginOffset"]] + f"[{ent['Type']}]" + text[ent["EndOffset"]:]
    return text


def process_document(doc: dict) -> dict:
    text_fields = [k for k, v in doc.items() if isinstance(v, str) and len(v) > 20]
    all_entities = []

    combined = " ".join(doc[f] for f in text_fields)
    if not combined or not contains_pii(combined):
        doc["pii_flag"] = False
        doc["pii_count"] = 0
        doc["pii_types"] = []
        doc["pii_scanned_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return doc

    for field in text_fields:
        entities = detect_pii(doc[field])
        if entities:
            all_entities.extend(entities)
            if PII_HANDLING_MODE == "REDACT":
                doc[field] = redact_text(doc[field], entities)

    doc["pii_flag"] = len(all_entities) > 0
    doc["pii_count"] = len(all_entities)
    doc["pii_types"] = list({e["Type"] for e in all_entities})
    doc["pii_scanned_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return doc


def handle_s3_event(event):
    """Process documents from S3 trigger."""
    client = get_os_client()
    results = []

    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]

        obj = s3.get_object(Bucket=bucket, Key=key)
        body = obj["Body"].read().decode("utf-8")

        if key.endswith(".json"):
            data = json.loads(body)
            docs = data if isinstance(data, list) else [data]
        else:
            docs = [{"source_key": key, "body": body}]

        for doc in docs:
            processed = process_document(doc)
            client.index(index=OPENSEARCH_INDEX, body=processed)
            results.append({"key": key, "pii_flag": processed["pii_flag"], "types": processed["pii_types"]})

    return {"processed": len(results), "results": results}


def handle_scheduled_scan(event):
    """Scan unscanned docs in OpenSearch (EventBridge trigger)."""
    client = get_os_client()
    query = {"query": {"bool": {"must_not": {"exists": {"field": "pii_flag"}}}}}

    total_scanned = 0
    total_flagged = 0

    while True:
        resp = client.search(index=OPENSEARCH_INDEX, body={**query, "size": BATCH_SIZE})
        hits = resp["hits"]["hits"]
        if not hits:
            break

        bulk_body = ""
        for hit in hits:
            processed = process_document(hit["_source"])
            action = json.dumps({"index": {"_index": OPENSEARCH_INDEX, "_id": hit["_id"]}})
            bulk_body += action + "\n" + json.dumps(processed) + "\n"
            total_scanned += 1
            if processed["pii_flag"]:
                total_flagged += 1

        client.bulk(body=bulk_body, refresh="wait_for")

        if len(hits) < BATCH_SIZE:
            break

    return {"scanned": total_scanned, "flagged": total_flagged}


def handle_direct_invoke(event):
    """Process a single document passed directly."""
    doc = event.get("document", event)
    processed = process_document(doc)

    if event.get("index", True):
        client = get_os_client()
        client.index(index=OPENSEARCH_INDEX, body=processed, refresh="wait_for")

    return {"pii_flag": processed["pii_flag"], "pii_types": processed["pii_types"], "pii_count": processed["pii_count"]}


def handler(event, context):
    """Route to appropriate handler based on event source."""
    if "Records" in event and event["Records"][0].get("eventSource") == "aws:s3":
        return handle_s3_event(event)
    elif event.get("source") == "aws.events" or event.get("detail-type") == "Scheduled Event":
        return handle_scheduled_scan(event)
    else:
        return handle_direct_invoke(event)
