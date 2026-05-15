import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

REGION = os.environ.get("AWS_REGION", "us-east-1")

OPENSEARCH_ENDPOINT = os.environ.get("OPENSEARCH_ENDPOINT")
if not OPENSEARCH_ENDPOINT:
    print("ERROR: OPENSEARCH_ENDPOINT environment variable is required.", file=sys.stderr)
    print("  Set it to your OpenSearch domain hostname (no https://)", file=sys.stderr)
    print("  Example: export OPENSEARCH_ENDPOINT=vpc-my-domain.us-east-1.es.amazonaws.com", file=sys.stderr)
    sys.exit(1)

OPENSEARCH_INDEX = os.environ.get("OPENSEARCH_INDEX", "pii-test")
COMPREHEND_LANGUAGE = os.environ.get("COMPREHEND_LANGUAGE", "en")
PII_HANDLING_MODE = os.environ.get("PII_HANDLING_MODE", "REDACT")  # REDACT or FLAG
PII_CONFIDENCE_THRESHOLD = float(os.environ.get("PII_CONFIDENCE_THRESHOLD", "0.7"))

PII_ENTITY_TYPES = [
    "NAME", "SSN", "CREDIT_DEBIT_NUMBER", "EMAIL",
    "PHONE", "ADDRESS", "DATE_TIME", "BANK_ACCOUNT_NUMBER",
]
