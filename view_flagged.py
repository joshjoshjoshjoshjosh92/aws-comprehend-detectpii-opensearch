"""View documents flagged as containing PII."""
import argparse
from config import OPENSEARCH_INDEX
from os_client import get_client


def view_flagged(limit: int = 10):
    client = get_client()
    query = {
        "query": {"term": {"pii_flag": True}},
        "size": limit,
        "sort": [{"pii_scanned_at": {"order": "desc"}}],
    }
    resp = client.search(index=OPENSEARCH_INDEX, body=query)
    hits = resp["hits"]["hits"]

    if not hits:
        print("No flagged documents found.")
        return

    print(f"Showing {len(hits)} flagged document(s):\n")
    for hit in hits:
        src = hit["_source"]
        print(f"  ID: {hit['_id']}")
        print(f"  PII types: {src.get('pii_types', [])}")
        print(f"  PII count: {src.get('pii_count', 0)}")
        print(f"  Scanned:   {src.get('pii_scanned_at', 'N/A')}")
        text_fields = [k for k, v in src.items() if isinstance(v, str) and len(v) > 20
                       and k not in ("pii_scanned_at",)]
        for f in text_fields[:2]:
            print(f"  {f}: {src[f][:120]}...")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    view_flagged(args.limit)
