# Architecture Guide

## Overview

This solution provides automated PII detection and redaction for documents in Amazon OpenSearch Service. It supports three deployment modes optimized for different scale and cost requirements.

---

## Architecture Modes

### Mode 1: EC2 (Always-On Processor)

Best for: Development, demos, always-on processing with SSM access.

```
┌─────────────────┐     ┌──────────────────────────┐     ┌─────────────────────────┐
│   Data Source   │────▶│   EC2 Instance (Private)  │────▶│  Amazon OpenSearch      │
│  (S3 / Local)   │     │   - pii_processor.py      │     │  (Private Subnet)       │
└─────────────────┘     │   - detect_pii.py         │     │  - Sanitized Index      │
                        └────────────┬─────────────┘     │  - PII Metadata         │
                                     │                    └─────────────────────────┘
                                     ▼
                            ┌──────────────────┐
                            │Amazon Comprehend  │
                            │ ContainsPii (cheap)│
                            │ DetectPii (full)  │
                            └──────────────────┘
```

**Cost:** ~$15.55/month (t3.small EC2 + Comprehend usage)

---

### Mode 2: Serverless (Lambda + EventBridge)

Best for: Production workloads with variable volume. Zero cost when idle.

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────────────┐
│   S3 Bucket     │────▶│  AWS Lambda       │────▶│  Amazon OpenSearch       │
│  (New docs)     │     │  (VPC-attached)   │     │  (Private Subnet)        │
└─────────────────┘     └────────┬─────────┘     └──────────────────────────┘
                                 │
┌─────────────────┐              │
│  EventBridge    │──────────────┘
│  (Schedule)     │     Triggers scan of unscanned docs
└─────────────────┘              │
                                 ▼
                        ┌──────────────────┐
                        │Amazon Comprehend  │
                        └──────────────────┘
```

**Triggers:**
- **S3 Event:** New document uploaded → Lambda invoked → PII detected → indexed to OpenSearch
- **EventBridge Schedule:** Every N minutes → Lambda scans unscanned docs in OpenSearch
- **Direct Invoke:** API call with document payload

**Cost:** ~$0.65/month for 10K docs (Lambda invocations + Comprehend)

---

### Mode 3: Batch (Async Comprehend Jobs)

Best for: Large backfills (10K+ docs), one-time migrations, lowest possible cost.

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  OpenSearch     │────▶│   S3 (Input)      │────▶│  Comprehend      │────▶│  S3 (Output)    │
│  (Unscanned)    │     │  (JSONL export)   │     │  Batch Job       │     │  (Results)      │
└─────────────────┘     └──────────────────┘     └──────────────────┘     └────────┬────────┘
                                                                                     │
                        ┌──────────────────────────────────────────────────────────────┘
                        ▼
               ┌─────────────────┐
               │  OpenSearch     │
               │  (Updated with  │
               │   PII metadata) │
               └─────────────────┘
```

**Cost:** ~$0.38/month for 10K docs (50% cheaper Comprehend pricing for async jobs)

---

## Detection Flow (All Modes)

```
Document arrives
       │
       ▼
┌─────────────────────────────┐
│ 1. Extract text fields      │  Fields > 20 chars
│    (title, body, notes...)  │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ 2. ContainsPiiEntities      │  $0.000025/unit (CHEAP)
│    "Does this have PII?"    │
└──────────────┬──────────────┘
               │
          ┌────┴────┐
          │         │
         NO        YES
          │         │
          ▼         ▼
┌──────────┐  ┌─────────────────────────────┐
│ Mark as  │  │ 3. DetectPiiEntities        │  $0.0001/unit
│ clean    │  │    Get exact spans + types  │
│ pii_flag │  └──────────────┬──────────────┘
│ = false  │                 │
└──────────┘                 ▼
                   ┌─────────────────────────────┐
                   │ 4. Redact or Flag           │
                   │    REDACT: [NAME] [SSN]...  │
                   │    FLAG: metadata only      │
                   └──────────────┬──────────────┘
                                  │
                                  ▼
                   ┌─────────────────────────────┐
                   │ 5. Index to OpenSearch       │
                   │    + pii_flag: true          │
                   │    + pii_types: [NAME, SSN]  │
                   │    + pii_count: 4            │
                   │    + pii_scanned_at: <ts>    │
                   └─────────────────────────────┘
```

---

## Network Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  VPC (10.0.0.0/16)                                              │
│                                                                  │
│  ┌─────────────────────────────┐  ┌──────────────────────────┐ │
│  │  Public Subnet (10.0.2.0/24)│  │ Private Subnet (10.0.1.0)│ │
│  │                             │  │                           │ │
│  │  ┌─────────────────┐       │  │  ┌───────────────────┐   │ │
│  │  │  NAT Gateway    │       │  │  │  EC2 / Lambda     │   │ │
│  │  └────────┬────────┘       │  │  │  (Processor)      │   │ │
│  │           │                 │  │  └─────────┬─────────┘   │ │
│  └───────────┼─────────────────┘  │            │              │ │
│              │                     │            │ SG: 443 only │ │
│              │                     │            ▼              │ │
│              │                     │  ┌───────────────────┐   │ │
│              │                     │  │  OpenSearch       │   │ │
│              │                     │  │  (VPC Endpoint)   │   │ │
│              │                     │  └───────────────────┘   │ │
│              │                     │                           │ │
│  ┌───────────┼─────────────────┐  └──────────────────────────┘ │
│  │  Internet Gateway           │                                 │
│  └─────────────────────────────┘                                 │
└─────────────────────────────────────────────────────────────────┘
                    │
                    ▼
         ┌──────────────────┐
         │ Comprehend API   │  (via NAT → Internet → AWS endpoint)
         │ CloudWatch Logs  │
         │ SSM Endpoint     │
         └──────────────────┘
```

---

## Security Controls

| Layer | Control | Implementation |
|-------|---------|----------------|
| Network | No public endpoints | OpenSearch + EC2/Lambda in private subnet |
| Network | Egress restricted | Security group allows only HTTPS (443) outbound |
| Network | Ingress restricted | OpenSearch SG only accepts traffic from processor SG |
| Network | Audit trail | VPC Flow Logs → CloudWatch (30-day retention) |
| Encryption | In transit | TLS 1.2 enforced on all connections |
| Encryption | At rest | OpenSearch encryption at rest enabled |
| Encryption | Node-to-node | OpenSearch node-to-node encryption enabled |
| IAM | Least privilege | Comprehend: read-only. OpenSearch: Post/Put/Get only |
| IAM | No long-term creds | EC2 instance role / Lambda execution role (STS) |
| Access | No SSH required | SSM Session Manager for EC2 access |
| Data | PII never persisted raw | Redacted before indexing; only entity types logged |
| Compliance | Audit log | CloudWatch log group with 90-day retention |

---

## OpenSearch Index Schema

Documents are indexed with the following PII metadata fields:

```json
{
  "title": "Account Opening Request",
  "body": "Please open an account for [NAME]. SSN [SSN]. Contact at [EMAIL]...",
  "pii_flag": true,
  "pii_count": 5,
  "pii_types": ["NAME", "SSN", "EMAIL", "PHONE", "ADDRESS"],
  "pii_scanned_at": "2025-05-15T00:57:00Z"
}
```

**Index mappings:**

| Field | Type | Purpose |
|-------|------|---------|
| `pii_flag` | boolean | Quick filter: has PII or not |
| `pii_count` | integer | Number of PII entities detected |
| `pii_types` | keyword[] | Which PII types were found (aggregatable) |
| `pii_scanned_at` | date | When the scan occurred |

---

## Scalability Characteristics

| Dimension | EC2 Mode | Serverless Mode | Batch Mode |
|-----------|----------|-----------------|------------|
| Max throughput | ~8 docs/sec (Comprehend TPS) | ~1000 concurrent Lambdas | Unlimited (async) |
| Latency | Real-time | Real-time (S3 trigger) or scheduled | Minutes to hours |
| Idle cost | ~$15/month | $0 | $0 |
| Throttle handling | Retry with backoff | Lambda concurrency controls | N/A (async) |
| Max doc size | 100KB (Comprehend limit) | 100KB | 100KB |
