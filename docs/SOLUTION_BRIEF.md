# Solution Brief: Automated PII Detection & Redaction for Amazon OpenSearch

> **AWS PACE Program — Financial Services Industry Segment**

---

## Problem Statement

Financial services organizations ingest millions of documents into Amazon OpenSearch Service for search, analytics, and compliance reporting. These documents frequently contain Personally Identifiable Information (PII) — names, SSNs, account numbers, addresses — that must be detected and redacted before it reaches downstream consumers.

Existing approaches are either:
- **Manual** — compliance teams review documents post-hoc (slow, error-prone, doesn't scale)
- **Regex-based** — pattern matching misses context-dependent PII (names, addresses) and generates false positives
- **Expensive** — calling full NLP detection on every document regardless of content

There is no published AWS reference architecture that combines cost-optimized Comprehend PII detection with OpenSearch in a production-ready, one-click-deployable pattern.

---

## Solution

A serverless, cost-optimized pipeline that automatically detects and redacts PII in documents indexed into Amazon OpenSearch Service using Amazon Comprehend as the NLP engine.

**What makes this novel:**

1. **Two-tier detection strategy** — Uses `ContainsPiiEntities` ($0.000025/unit) as a cheap pre-filter before calling `DetectPiiEntities` ($0.0001/unit). Clean documents never hit the expensive API. This pattern is not documented in any existing AWS guidance.

2. **Three deployment modes** — EC2 (always-on), Lambda/EventBridge (serverless, zero idle cost), and Comprehend async batch jobs (50% cheaper for large volumes). Customer picks based on their volume and latency requirements.

3. **One-click CloudFormation deployment** — Full stack (VPC, OpenSearch, compute, IAM, logging) deploys in a single command. Customer is running the demo in 15 minutes.

4. **97% cost reduction** vs. naïve implementation — Serverless + pre-filter + batch processing reduces a $16/month workload to $0.38/month at 10K documents.

---

## AWS Services Used

| Service | Role | Cost Driver |
|---------|------|-------------|
| Amazon Comprehend | PII entity detection & classification | Per-unit API pricing |
| Amazon OpenSearch Service | Document storage, search, analytics | Instance hours + storage |
| AWS Lambda | Serverless document processing | Per-invocation + duration |
| Amazon EventBridge | Scheduled scan triggers | Free tier covers most usage |
| Amazon S3 | Batch job input/output staging | Storage + requests |
| AWS CloudFormation | Infrastructure deployment | Free |
| Amazon CloudWatch | VPC Flow Logs, audit logging | Log ingestion + storage |
| AWS Systems Manager | Secure instance access (SSM) | Free |

---

## Target Customer Profile

- **Industry:** Financial Services, Healthcare, Legal, Insurance
- **Compliance drivers:** GLBA, SOX, CCPA, HIPAA, GDPR
- **Technical profile:** Teams using OpenSearch for document search/analytics who need automated PII governance
- **Volume:** 1K–1M+ documents/month
- **Decision maker:** CISO, Chief Data Officer, Compliance Engineering Lead

---

## Key Metrics

| Metric | Value |
|--------|-------|
| Deployment time | ~15 minutes (CloudFormation) |
| PII detection accuracy | >95% (Comprehend benchmark) |
| Cost per 10K docs (serverless) | ~$0.65 |
| Cost per 10K docs (batch) | ~$0.38 |
| Cost reduction vs. naïve | 97% |
| Supported PII types | 12+ (NAME, SSN, CC, EMAIL, PHONE, ADDRESS, etc.) |
| Languages supported | English (extensible via Comprehend) |

---

## Differentiation from Existing Solutions

| Existing Approach | Gap | This Solution |
|-------------------|-----|---------------|
| Comprehend + S3 only | No OpenSearch integration | Native OpenSearch indexing with PII metadata |
| OpenSearch Security Plugin | Only masks at query time, PII still stored | Redacts at ingest, PII never persisted |
| Macie | S3-only, no OpenSearch, no redaction | Full pipeline: detect → redact → index |
| Custom regex | Misses context-dependent PII | NLP-based detection via Comprehend |
| DetectPiiEntities on all docs | Expensive at scale | Pre-filter reduces cost 45-97% |

---

## Reuse & Accreditation

- **Program:** AWS PACE (Patterns, Automations, and Content for Engineers)
- **Segment:** Financial Services Industry
- **Asset type:** Reference Architecture + Working Implementation
- **Reuse tracking:** GitHub repository with issue/PR workflow for adaptation tracking
- **Author:** Joshua Walther, Technical Account Manager, Financial Services

---

## Links

- **Repository:** [github.com/joshjoshjoshjoshjosh92/aws-comprehend-detectpii-opensearch](https://github.com/joshjoshjoshjoshjosh92/aws-comprehend-detectpii-opensearch)
- **Quick Start:** See `QUICKSTART.md` in repository
- **Architecture Detail:** See `docs/ARCHITECTURE.md`
- **Implementation Guide:** See `docs/IMPLEMENTATION_GUIDE.md`
