import os

REGION = os.environ.get("AWS_REGION", "us-east-1")
OPENSEARCH_ENDPOINT = os.environ["OPENSEARCH_ENDPOINT"]  # hostname only, no https://
OPENSEARCH_INDEX = os.environ.get("OPENSEARCH_INDEX", "pii-test")
COMPREHEND_LANGUAGE = os.environ.get("COMPREHEND_LANGUAGE", "en")
PII_HANDLING_MODE = os.environ.get("PII_HANDLING_MODE", "REDACT")  # REDACT or FLAG

PII_ENTITY_TYPES = [
    "NAME", "SSN", "CREDIT_DEBIT_NUMBER", "EMAIL",
    "PHONE", "ADDRESS", "DATE_TIME", "BANK_ACCOUNT_NUMBER",
]
