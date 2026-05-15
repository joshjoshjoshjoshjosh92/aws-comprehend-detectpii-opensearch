import argparse
import json
import sys
import time
import boto3
from config import (
    REGION, OPENSEARCH_INDEX, COMPREHEND_LANGUAGE,
    PII_HANDLING_MODE, PII_ENTITY_TYPES, PII_CONFIDENCE_THRESHOLD,
)
from os_client import get_client


def _get_comprehend():
    return boto3.client("comprehend", region_name=REGION)


def contains_pii(text: str) -> bool:
    """Cheap pre-filter: returns True if text likely contains PII. ~4x cheaper than detect."""
    text = text[:99_000]
    resp = _get_comprehend().contains_pii_entities(Text=text, LanguageCode=COMPREHEND_LANGUAGE)
    return any(
        label["Score"] >= PII_CONFIDENCE_THRESHOLD
        and label["Name"] in PII_ENTITY_TYPES
        for label in resp.get("Labels", [])
    )


def detect_pii(text: str) -> list[dict]:
    """Call Comprehend DetectPiiEntities. Returns list of entity dicts."""
    text = text[:99_000]
    resp = _get_comprehend().detect_pii_entities(Text=text, LanguageCode=COMPREHEND_LANGUAGE)
    return [
        e for e in resp.get("Entities", [])
        if e["Type"] in PII_ENTITY_TYPES and e["Score"] >= PII_CONFIDENCE_THRESHOLD
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
    text_fields = [k for k, v in doc.items() if isinstance(v, str) and len(v) > 20]
    all_entities = []

    # Concatenate text for a single cheap pre-filter call
    combined = " ".join(doc[f] for f in text_fields)
    if not combined or not contains_pii(combined):
        doc["pii_flag"] = False
        doc["pii_count"] = 0
        doc["pii_types"] = []
        doc["pii_scanned_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return doc

    # Only call expensive DetectPiiEntities if pre-filter says PII exists
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


def bulk_index(client, docs: list[tuple], refresh: bool = False):
    """Bulk index a list of (doc, doc_id) tuples."""
    if not docs:
        return
    body = ""
    for doc, doc_id in docs:
        action = {"index": {"_index": OPENSEARCH_INDEX}}
        if doc_id:
            action["index"]["_id"] = doc_id
        body += json.dumps(action) + "\n" + json.dumps(doc) + "\n"
    client.bulk(body=body, refresh="wait_for" if refresh else False)


def process_file(path: str, mode: str):
    """Process a single JSON file (one doc or array of docs)."""
    with open(path) as f:
        data = json.load(f)

    docs = data if isinstance(data, list) else [data]
    client = get_client()
    batch = []

    for i, doc in enumerate(docs):
        processed = process_document(doc, mode)
        batch.append((processed, None))
        status = "PII FOUND" if processed["pii_flag"] else "clean"
        print(f"  [{i+1}/{len(docs)}] {status} — types: {processed['pii_types']}")

        if len(batch) >= 25:
            bulk_index(client, batch)
            batch = []

    bulk_index(client, batch, refresh=True)
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
