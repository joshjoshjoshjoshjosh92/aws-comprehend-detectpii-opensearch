"""Scan unscanned documents in OpenSearch for PII using Comprehend."""
import sys
import time
from config import OPENSEARCH_INDEX
from os_client import get_client
from pii_processor import process_document, index_document


def scan_unscanned(batch_size: int = 50):
    client = get_client()

    # Find docs that haven't been scanned yet
    query = {"query": {"bool": {"must_not": {"exists": {"field": "pii_flag"}}}}}
    resp = client.search(index=OPENSEARCH_INDEX, body={**query, "size": batch_size})
    hits = resp["hits"]["hits"]

    if not hits:
        print("All documents already scanned. Nothing to do.")
        return

    print(f"Found {len(hits)} unscanned document(s). Scanning...")

    flagged = 0
    for i, hit in enumerate(hits):
        doc = hit["_source"]
        for attempt in range(3):
            try:
                processed = process_document(doc)
                break
            except Exception as e:
                if "ThrottlingException" in str(e) and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise
        index_document(client, processed, doc_id=hit["_id"])
        if processed["pii_flag"]:
            flagged += 1
        status = "PII" if processed["pii_flag"] else "ok "
        print(f"  [{i+1}/{len(hits)}] {status} id={hit['_id']} types={processed['pii_types']}")
        # Pace to avoid Comprehend throttling (10 TPS default)
        if (i + 1) % 8 == 0:
            time.sleep(1)

    print(f"\nDone. Scanned {len(hits)}, flagged {flagged}.")


if __name__ == "__main__":
    batch = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    scan_unscanned(batch)
