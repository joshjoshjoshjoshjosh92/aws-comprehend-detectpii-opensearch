import argparse
import json
import sys
import time
import boto3
from config import REGION, OPENSEARCH_INDEX, COMPREHEND_LANGUAGE, PII_HANDLING_MODE, PII_ENTITY_TYPES
from os_client import get_client


comprehend = boto3.client("comprehend", region_name=REGION)


def detect_pii(text: str) -> list[dict]:
    """Call Comprehend DetectPiiEntities. Returns list of entity dicts."""
    # Comprehend has a 100KB limit per call
    text = text[:99_000]
    resp = comprehend.detect_pii_entities(Text=text, LanguageCode=COMPREHEND_LANGUAGE)
    return [
        e for e in resp.get("Entities", [])
        if e["Type"] in PII_ENTITY_TYPES and e["Score"] >= 0.7
    ]


def redact_text(text: str, entities: list[dict]) -> str:
    """Replace PII spans with [ENTITY_TYPE] tokens, working right-to-left."""
    sorted_ents = sorted(entities, key=lambda e: e["BeginOffset"], reverse=True)
    for ent in sorted_ents:
        start, end = ent["BeginOffset"], ent["EndOffset"]
        text = text[:start] + f"[{ent['Type']}]" + text[end:]
    return text


def process_document(doc: dict, mode: str = PII_HANDLING_MODE) -> dict:
    """Detect PII in a document's text fields, redact or flag, return enriched doc."""
    text_fields = [k for k, v in doc.items() if isinstance(v, str) and len(v) > 10]
    all_entities = []

    for field in text_fields:
        entities = detect_pii(doc[field])
        if entities:
            all_entities.extend(entities)
            if mode == "REDACT":
                doc[field] = redact_text(doc[field], entities)

    doc["pii_flag"] = len(all_entities) > 0
    doc["pii_count"] = len(all_entities)
    doc["pii_types"] = list({e["Type"] for e in all_entities})
    doc["pii_scanned_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return doc


def index_document(client, doc: dict, doc_id: str = None):
    """Index a processed document into OpenSearch."""
    client.index(index=OPENSEARCH_INDEX, body=doc, id=doc_id, refresh="wait_for")


def process_file(path: str, mode: str):
    """Process a single JSON file (one doc or array of docs)."""
    with open(path) as f:
        data = json.load(f)

    docs = data if isinstance(data, list) else [data]
    client = get_client()

    for i, doc in enumerate(docs):
        processed = process_document(doc, mode)
        index_document(client, processed)
        status = "PII FOUND" if processed["pii_flag"] else "clean"
        print(f"  [{i+1}/{len(docs)}] {status} — types: {processed['pii_types']}")

    print(f"\nDone. Processed {len(docs)} document(s) into index '{OPENSEARCH_INDEX}'.")


def main():
    parser = argparse.ArgumentParser(description="PII detection processor for OpenSearch")
    parser.add_argument("--input", help="Path to JSON document file")
    parser.add_argument("--mode", choices=["REDACT", "FLAG"], default=PII_HANDLING_MODE)
    args = parser.parse_args()

    if not args.input:
        print("Error: --input is required", file=sys.stderr)
        sys.exit(1)

    process_file(args.input, args.mode)


if __name__ == "__main__":
    main()
