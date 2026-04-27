# Amazon Comprehend + OpenSearch PII Detection

> **Published via the AWS PACE Program — Financial Services Industry Segment**

A production-ready reference architecture and implementation for automated PII detection and redaction in Amazon OpenSearch Service using Amazon Comprehend as the NLP detection engine. Built to address a financial services data governance requirement where Comprehend was the mandated detection service.

---

## Architecture Overview

This solution intercepts documents being indexed into OpenSearch, routes them through Amazon Comprehend for PII entity detection, redacts or flags identified PII, and stores the sanitized output — all without requiring changes to the upstream ingestion pipeline.

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────────────┐
│   Data Source   │────▶│    EC2 Instance   │────▶│  Amazon OpenSearch      │
│  (S3 / Stream)  │     │  (PII Processor)  │     │  (Sanitized Index)      │
└─────────────────┘     └────────┬─────────┘     └─────────────────────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │Amazon Comprehend  │
                         │ PII Detection API │
                         └──────────────────┘
```

**Core components:**

- **EC2 (Processing Layer)** — Python-based processor running on EC2 that orchestrates document ingestion, Comprehend API calls, and redaction logic before indexing into OpenSearch
- **Amazon Comprehend** — NLP service used to detect PII entities (names, SSNs, account numbers, dates of birth, addresses, etc.) via the `detect_pii_entities` API
- **Amazon OpenSearch Service** — Target search/analytics store receiving only sanitized, redacted documents
- **IAM Roles** — Least-privilege roles scoped to Comprehend read and OpenSearch write permissions

---

## Prerequisites

- AWS Account with appropriate permissions
- Python 3.8+
- AWS CLI configured (`aws configure`)
- An existing Amazon OpenSearch Service domain (or deploy a new one)
- EC2 instance with IAM role attached (see [IAM Setup](#iam-setup))

**Required Python packages:**

```bash
pip install boto3 opensearch-py requests requests-aws4auth
```

---

## IAM Setup

The EC2 instance role requires the following permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "comprehend:DetectPiiEntities",
        "comprehend:ContainsPiiEntities"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "es:ESHttpPost",
        "es:ESHttpPut",
        "es:ESHttpGet"
      ],
      "Resource": "arn:aws:es:<region>:<account-id>:domain/<your-domain>/*"
    }
  ]
}
```

---

## Configuration

Update `config.py` with your environment values:

```python
# AWS Region
REGION = "us-east-1"

# OpenSearch
OPENSEARCH_ENDPOINT = "https://<your-domain>.<region>.es.amazonaws.com"
OPENSEARCH_INDEX = "documents"

# Comprehend
COMPREHEND_LANGUAGE = "en"

# PII Handling: "REDACT" replaces PII with [PII_TYPE], "FLAG" adds metadata only
PII_HANDLING_MODE = "REDACT"

# PII entity types to act on (Comprehend supported types)
PII_ENTITY_TYPES = [
    "NAME", "SSN", "CREDIT_DEBIT_NUMBER", "EMAIL", 
    "PHONE", "ADDRESS", "DATE_TIME", "BANK_ACCOUNT_NUMBER"
]
```

---

## Usage

**Single document:**

```bash
python pii_processor.py --input document.json --mode REDACT
```

**Batch from S3:**

```bash
python pii_processor.py --source s3://your-bucket/documents/ --mode REDACT
```

**Run as a service on EC2:**

```bash
python pii_processor.py --daemon --poll-interval 30
```

---

## How It Works

1. **Ingest** — Documents are pulled from the configured source (S3, local, or stream)
2. **Detect** — Each document's text fields are passed to `comprehend.detect_pii_entities()`
3. **Redact/Flag** — Based on `PII_HANDLING_MODE`, identified entities are either replaced inline with `[ENTITY_TYPE]` tokens or flagged as metadata
4. **Index** — The sanitized document is indexed into OpenSearch with an audit trail field (`pii_detected: true/false`, entity counts by type)
5. **Log** — All PII detection events are logged for compliance auditing

---

## PII Entity Coverage

Comprehend detects the following entity types (configurable in `config.py`):

| Entity Type | Example |
|---|---|
| `NAME` | John Smith |
| `SSN` | 123-45-6789 |
| `CREDIT_DEBIT_NUMBER` | 4111 1111 1111 1111 |
| `EMAIL` | user@example.com |
| `PHONE` | (555) 867-5309 |
| `ADDRESS` | 123 Main St, Seattle WA |
| `DATE_TIME` | January 1, 1980 |
| `BANK_ACCOUNT_NUMBER` | 000123456789 |

---

## FSI Compliance Considerations

This solution was designed with financial services data governance requirements in mind:

- **No PII persisted in transit** — Comprehend API calls are made over TLS; raw PII never touches the OpenSearch index
- **Audit logging** — Every document processed generates a structured log entry with entity types detected (not values) for compliance reporting
- **Least-privilege IAM** — EC2 role scoped to minimum required Comprehend and OpenSearch permissions
- **Configurable entity scope** — Teams can restrict detection to specific PII types relevant to their regulatory context (GLBA, SOX, CCPA)

---

## PACE Publication

This solution is published as part of the **AWS PACE (Patterns, Automations, and Content for Engineers) Program** for the Financial Services Industry segment. It is recognized in Amazon's internal reuse tracking system as a repeatable GTM asset.

---

## Contributing

This is a published reference architecture. If you adapt it for a customer engagement or extend it for a new use case, please:

1. Open an issue or PR describing the extension
2. Tag the owning SA team so reuse can be tracked for program accreditation

---

## Author

**Joshua** — AWS Technical Account Manager, Financial Services  
Built in response to a customer spec-req; published to the FSI SA community via PACE.

---

## License

This project is intended for internal AWS use and customer-facing reference implementations. Refer to your AWS PACE program guidelines for redistribution terms.
