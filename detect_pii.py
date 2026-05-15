"""Scan unscanned documents in OpenSearch for PII using Comprehend."""
import sys
import time
from config import OPENSEARCH_INDEX
from os_client import get_client
from pii_processor import process_document, bulk_index


def scan_unscanned(batch_size: int = 50, max_docs: int = None):
    """Paginate through all unscanned docs and process them."""
    client = get_client()
    query = {"query": {"bool": {"must_not": {"exists": {"field": "pii_flag"}}}}}

    total_scanned = 0
    total_flagged = 0
    keep_going = True

    while keep_going:
        limit = batch_size
        if max_docs:
            limit = min(batch_size, max_docs - total_scanned)
            if limit <= 0:
                break

        resp = client.search(index=OPENSEARCH_INDEX, body={**query, "size": limit})
        hits = resp["hits"]["hits"]

        if not hits:
            break

        if total_scanned == 0:
            total_available = resp["hits"]["total"]["value"]
            cap = f" (capped at {max_docs})" if max_docs else ""
            print(f"Found {total_available} unscanned document(s){cap}. Scanning...")

        batch = []
        for i, hit in enumerate(hits):
            doc = hit["_source"]
            for attempt in range(3):
                try:
                    processed = process_document(doc)
                    break
                except Exception as e:
                    if "ThrottlingException" in str(e) and attempt < 2:
                        time.sleep(2 ** (attempt + 1))
                        continue
                    raise

            batch.append((processed, hit["_id"]))
            if processed["pii_flag"]:
                total_flagged += 1
            total_scanned += 1

            status = "PII" if processed["pii_flag"] else "ok "
            print(f"  [{total_scanned}] {status} id={hit['_id']} types={processed['pii_types']}")

            # Pace to stay under Comprehend default 10 TPS
            if total_scanned % 8 == 0:
                time.sleep(1)

        # Bulk index the batch
        bulk_index(client, batch, refresh=True)

        # If we got fewer than requested, we're done
        if len(hits) < limit:
            keep_going = False

    if total_scanned == 0:
        print("All documents already scanned. Nothing to do.")
    else:
        print(f"\nDone. Scanned {total_scanned}, flagged {total_flagged}.")


if __name__ == "__main__":
    batch = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    max_d = int(sys.argv[2]) if len(sys.argv) > 2 else None
    scan_unscanned(batch, max_d)
