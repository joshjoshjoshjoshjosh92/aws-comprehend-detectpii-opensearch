# Cost Estimate

Detailed cost breakdown for operating this solution at various scales. All prices are US East (N. Virginia) as of 2025.

---

## Pricing Components

| Service | Pricing Model | Unit Cost |
|---------|---------------|-----------|
| Comprehend `ContainsPiiEntities` | Per 100-char unit | $0.000025/unit |
| Comprehend `DetectPiiEntities` | Per 100-char unit | $0.0001/unit |
| Comprehend Async Batch Job | Per 100-char unit | $0.00005/unit |
| OpenSearch `t3.small.search` | Per hour | $0.036/hr (~$26/month) |
| OpenSearch EBS (gp3) | Per GB/month | $0.08/GB |
| EC2 `t3.small` | Per hour | $0.0208/hr (~$15/month) |
| Lambda | Per 1ms (512MB) | $0.0000000083/ms |
| Lambda | Per request | $0.0000002/request |
| NAT Gateway | Per hour + data | $0.045/hr + $0.045/GB |
| CloudWatch Logs | Ingestion | $0.50/GB |
| S3 (batch staging) | Storage + requests | $0.023/GB + $0.005/1K PUT |

---

## Scenario 1: Small (1,000 docs/month)

Assumes: avg 500 chars/doc (5 units), 30% PII rate.

| Component | EC2 Mode | Serverless Mode |
|-----------|----------|-----------------|
| Comprehend pre-filter (1000 docs) | $0.025 | $0.025 |
| Comprehend full detect (300 docs) | $0.015 | $0.015 |
| OpenSearch (t3.small + 20GB) | $27.60 | $27.60 |
| Compute (EC2 or Lambda) | $15.00 | $0.01 |
| NAT Gateway | $32.40 | $32.40 |
| CloudWatch Logs | $0.10 | $0.10 |
| **Total** | **~$75/month** | **~$60/month** |

> Note: OpenSearch and NAT Gateway dominate at small scale. For cost-sensitive small deployments, consider OpenSearch Serverless or VPC endpoints for Comprehend.

---

## Scenario 2: Medium (10,000 docs/month)

Assumes: avg 500 chars/doc (5 units), 30% PII rate.

| Component | EC2 Mode | Serverless Mode | Batch Mode |
|-----------|----------|-----------------|------------|
| Comprehend pre-filter | $0.25 | $0.25 | — |
| Comprehend detect/batch | $0.15 | $0.15 | $0.13 |
| OpenSearch (t3.small + 20GB) | $27.60 | $27.60 | $27.60 |
| Compute | $15.00 | $0.10 | $0.10 |
| NAT Gateway | $32.40 | $32.40 | $32.40 |
| S3 (batch staging) | — | — | $0.01 |
| **Total** | **~$75/month** | **~$61/month** | **~$60/month** |

---

## Scenario 3: Large (100,000 docs/month)

Assumes: avg 500 chars/doc (5 units), 30% PII rate.

| Component | EC2 Mode | Serverless Mode | Batch Mode |
|-----------|----------|-----------------|------------|
| Comprehend pre-filter | $2.50 | $2.50 | — |
| Comprehend detect/batch | $1.50 | $1.50 | $1.25 |
| OpenSearch (m5.large + 50GB) | $120.00 | $120.00 | $120.00 |
| Compute | $15.00 | $1.00 | $0.50 |
| NAT Gateway | $32.40 | $32.40 | $32.40 |
| S3 (batch staging) | — | — | $0.10 |
| **Total** | **~$172/month** | **~$157/month** | **~$154/month** |

---

## Scenario 4: Enterprise (1,000,000 docs/month)

Assumes: avg 500 chars/doc (5 units), 30% PII rate.

| Component | Serverless Mode | Batch Mode |
|-----------|-----------------|------------|
| Comprehend pre-filter | $25.00 | — |
| Comprehend detect/batch | $15.00 | $12.50 |
| OpenSearch (3x m5.large + 200GB) | $375.00 | $375.00 |
| Compute (Lambda) | $10.00 | $5.00 |
| NAT Gateway | $32.40 | $32.40 |
| S3 (batch staging) | — | $1.00 |
| **Total** | **~$457/month** | **~$426/month** |

---

## Cost Optimization Levers

| Lever | Savings | How |
|-------|---------|-----|
| Pre-filter with `ContainsPiiEntities` | 45% on Comprehend | Skip expensive API for clean docs |
| Async batch jobs | 50% on Comprehend | Use `StartPiiEntitiesDetectionJob` for bulk |
| Serverless compute | 90-99% on compute | Lambda vs. always-on EC2 |
| Higher confidence threshold | Variable | Fewer entities = fewer redaction passes |
| Restrict entity types | Variable | Only detect what you need |
| OpenSearch Reserved Instances | ~30% on OpenSearch | 1-year RI commitment |
| VPC Endpoints (Comprehend) | ~100% on NAT data | Eliminate NAT Gateway data charges |

---

## Cost vs. Alternatives

| Approach | Monthly Cost (10K docs) | Notes |
|----------|------------------------|-------|
| Manual compliance review | $5,000+ | Human reviewers, slow, error-prone |
| Third-party DLP tool | $500-2,000 | License fees, integration complexity |
| Custom regex pipeline | $75 (infra only) | Misses context-dependent PII, high false positive rate |
| **This solution (serverless)** | **~$61** | NLP-accurate, automated, auditable |
| **This solution (batch)** | **~$60** | Lowest cost for bulk processing |

---

## AWS Pricing Calculator

For a customized estimate based on your specific volume and configuration:

https://calculator.aws

Select: Amazon Comprehend, Amazon OpenSearch Service, AWS Lambda, Amazon VPC (NAT Gateway)
