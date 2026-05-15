"""Seed OpenSearch with test documents containing known PII patterns."""
from config import OPENSEARCH_INDEX
from os_client import get_client

SAMPLE_DOCS = [
    {
        "title": "Account Opening Request",
        "body": "Please open an account for John Smith. SSN is 123-45-6789. "
                "Contact at john.smith@example.com or (555) 867-5309. "
                "Mailing address: 742 Evergreen Terrace, Springfield IL 62704.",
    },
    {
        "title": "Wire Transfer Memo",
        "body": "Transfer $50,000 from account 9876543210 to Maria Garcia at "
                "1600 Pennsylvania Ave, Washington DC 20500. Authorized by James Wilson on January 15, 1985.",
    },
    {
        "title": "Clean Internal Memo",
        "body": "Q4 planning meeting moved to Thursday. Please update your calendars. "
                "No action items from last week's sync.",
    },
    {
        "title": "Customer Complaint",
        "body": "Robert Johnson called regarding unauthorized charges on card 4111-1111-1111-1111. "
                "Customer DOB March 12, 1982. Callback number 206-555-0147.",
    },
    {
        "title": "Compliance Report",
        "body": "Quarterly AML review complete. No suspicious activity detected across "
                "monitored accounts. Next review scheduled for Q2.",
    },
]


def seed():
    client = get_client()

    # Ensure index exists
    if not client.indices.exists(index=OPENSEARCH_INDEX):
        client.indices.create(index=OPENSEARCH_INDEX, body={
            "mappings": {
                "properties": {
                    "pii_flag": {"type": "boolean"},
                    "pii_count": {"type": "integer"},
                    "pii_types": {"type": "keyword"},
                    "pii_scanned_at": {"type": "date"},
                }
            }
        })
        print(f"Created index '{OPENSEARCH_INDEX}'.")

    print(f"Indexing {len(SAMPLE_DOCS)} test documents...")
    for i, doc in enumerate(SAMPLE_DOCS):
        client.index(index=OPENSEARCH_INDEX, body=doc, refresh="wait_for")
        print(f"  [{i+1}] {doc['title']}")

    print("Done.")


if __name__ == "__main__":
    seed()
