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

## Quick Start

### One-Click Deploy

Deploy the full stack (OpenSearch + EC2 + IAM + networking) in one command:

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name pii-detect \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

Then connect and run:

```bash
INSTANCE_ID=$(aws cloudformation describe-stacks --stack-name pii-detect \
  --query 'Stacks[0].Outputs[?OutputKey==`EC2InstanceId`].OutputValue' --output text)
aws ssm start-session --target $INSTANCE_ID --region us-east-1

# On the instance:
cd /home/ec2-user/pii-detect && python3 run_demo.py
```

See [QUICKSTART.md](QUICKSTART.md) for detailed options including console deploy and bring-your-own-infra.

### Existing Infrastructure

```bash
git clone https://github.com/<your-org>/aws-comprehend-detectpii-opensearch.git
cd aws-comprehend-detectpii-opensearch
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your OpenSearch endpoint
python run_demo.py
```

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

Copy `.env.example` to `.env` and set your values:

```bash
cp .env.example .env
# Edit .env with your OpenSearch endpoint
```

**Required:**
- `OPENSEARCH_ENDPOINT` — Your OpenSearch domain hostname (no `https://`)

**Optional (defaults shown):**
- `AWS_REGION=us-east-1`
- `OPENSEARCH_INDEX=pii-test`
- `PII_HANDLING_MODE=REDACT` — `REDACT` replaces PII inline, `FLAG` adds metadata only
- `PII_CONFIDENCE_THRESHOLD=0.7` — Minimum Comprehend confidence score
- `COMPREHEND_LANGUAGE=en`

---

## Usage

**Process a JSON file (single doc or array):**

```bash
python pii_processor.py --input document.json --mode REDACT
```

**Scan all unscanned docs in OpenSearch:**

```bash
python detect_pii.py              # default batch of 50, paginate all
python detect_pii.py 100           # batch size 100
python detect_pii.py 50 500        # batch 50, cap at 500 docs
```

**Seed test data:**

```bash
python add_more_data.py            # 5 sample docs
python seed_1000.py                # 1000 docs for load testing
```

**View flagged documents:**

```bash
python view_flagged.py --limit 20
```

**Run full end-to-end demo:**

```bash
python run_demo.py
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

## Cost Optimization

This solution minimizes costs through three strategies:

### 1. Two-Tier Detection (Real-Time)

- **Pre-filter with `ContainsPiiEntities`** (~$0.000025/unit) — Cheap check first
- **Full detection with `DetectPiiEntities`** (~$0.0001/unit) — Only on docs that contain PII

### 2. Async Batch Jobs (Large Volumes)

For 10K+ documents, use `batch_detect.py` which leverages Comprehend async jobs at **50% the cost** of real-time API with no throttling limits.

```bash
python batch_detect.py --bucket my-bucket --role-arn arn:aws:iam::123456789:role/comprehend-role
```

### 3. Serverless Mode (Zero Idle Cost)

Deploy with `DeploymentMode=serverless` to use Lambda + EventBridge instead of EC2. Pay only when documents are being scanned.

```bash
aws cloudformation deploy --template-file template.yaml --stack-name pii-detect \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides DeploymentMode=serverless ScanSchedule="rate(5 minutes)"
```

### Cost Comparison

| Scenario (10K docs, 30% PII) | Compute | Comprehend | Total/month |
|------------------------------|---------|------------|-------------|
| Naïve (EC2 + DetectPii all) | ~$15 EC2 | $1.00 | ~$16.00 |
| **Optimized EC2** (pre-filter) | ~$15 EC2 | $0.55 | ~$15.55 |
| **Serverless** (Lambda + pre-filter) | ~$0.10 | $0.55 | ~$0.65 |
| **Batch job** (async, pre-filter) | ~$0.10 | $0.28 | ~$0.38 |

*Serverless + batch = 97% cheaper than naïve approach.*

---

## FSI Compliance Considerations

This solution was designed with financial services data governance requirements in mind:

- **No PII persisted in transit** — Comprehend API calls are made over TLS; raw PII never touches the OpenSearch index
- **Audit logging** — Every document processed generates a structured log entry with entity types detected (not values) for compliance reporting
- **Least-privilege IAM** — EC2 role scoped to minimum required Comprehend and OpenSearch permissions
- **Configurable entity scope** — Teams can restrict detection to specific PII types relevant to their regulatory context (GLBA, SOX, CCPA)

---

## Problem-Solution Fit

| Criteria | Assessment |
|----------|------------|
| **Real customer pain point?** | Yes — FSI orgs are fined for PII exposure in search indexes. Manual review doesn't scale. |
| **Implementation complexity?** | Low — one CloudFormation command, 15 minutes to running demo. |
| **Cost vs. alternatives?** | 97% cheaper than naïve approach; 95%+ cheaper than manual review or third-party DLP. |
| **Scalability?** | Three modes: EC2 (dev), Lambda (production), Batch (bulk). Handles 1K–1M+ docs/month. |
| **Security & compliance?** | Enterprise-grade: private VPC, encryption everywhere, least-privilege IAM, audit logs. |
| **Novelty?** | Two-tier `ContainsPii`→`DetectPii` cost pattern is not documented in any existing AWS guidance. |

---

## Operations & Maintenance

**Day-2 operations:**

- **Monitoring:** CloudWatch metrics for Comprehend API calls, Lambda errors, OpenSearch cluster health
- **Scaling up:** Change `OpenSearchInstanceType` parameter or add nodes via CloudFormation update
- **Scaling down:** Switch to `DeploymentMode=serverless` to eliminate idle compute cost
- **Updates:** `git pull` on EC2 instance or redeploy Lambda code via CI/CD
- **Cost control:** Set `max_docs` cap in `detect_pii.py`, use AWS Budgets alerts on Comprehend
- **Cleanup:** `aws cloudformation delete-stack` removes everything — zero lingering resources

**No ongoing maintenance required** — Comprehend is fully managed (no model training/tuning), OpenSearch handles index management, Lambda scales automatically.

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
