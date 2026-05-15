# Customized Examples

Real-world scenarios showing how to adapt this solution for different industries and use cases.

---

## Example 1: Financial Services — Loan Document Processing

**Scenario:** A bank ingests loan applications into OpenSearch for search and compliance review. Documents contain applicant names, SSNs, income details, and addresses that must be redacted before analyst access.

**Configuration:**
```bash
# .env
OPENSEARCH_ENDPOINT=vpc-loans-domain.us-east-1.es.amazonaws.com
OPENSEARCH_INDEX=loan-applications
PII_HANDLING_MODE=REDACT
PII_CONFIDENCE_THRESHOLD=0.8
```

**Custom entity types** (edit `config.py`):
```python
PII_ENTITY_TYPES = [
    "NAME", "SSN", "ADDRESS", "PHONE", "EMAIL",
    "BANK_ACCOUNT_NUMBER", "CREDIT_DEBIT_NUMBER", "DATE_TIME",
]
```

**Sample input document:**
```json
{
  "application_id": "LOAN-2025-00142",
  "applicant_name": "Sarah Johnson",
  "ssn": "987-65-4321",
  "annual_income": "$125,000",
  "employer": "Acme Corp",
  "address": "456 Oak Avenue, Portland OR 97201",
  "phone": "(503) 555-0198",
  "loan_amount": "$450,000",
  "loan_type": "30-year fixed mortgage"
}
```

**Output after redaction:**
```json
{
  "application_id": "LOAN-2025-00142",
  "applicant_name": "[NAME]",
  "ssn": "[SSN]",
  "annual_income": "$125,000",
  "employer": "Acme Corp",
  "address": "[ADDRESS]",
  "phone": "[PHONE]",
  "loan_amount": "$450,000",
  "loan_type": "30-year fixed mortgage",
  "pii_flag": true,
  "pii_count": 4,
  "pii_types": ["NAME", "SSN", "ADDRESS", "PHONE"],
  "pii_scanned_at": "2025-05-15T01:30:00Z"
}
```

**Compliance mapping:** GLBA (Gramm-Leach-Bliley Act), FCRA (Fair Credit Reporting Act)

---

## Example 2: Healthcare — Patient Record Indexing

**Scenario:** A health system indexes clinical notes into OpenSearch for provider search. PHI must be detected and flagged (not redacted) so compliance teams can review access patterns.

**Configuration:**
```bash
# .env
OPENSEARCH_INDEX=clinical-notes
PII_HANDLING_MODE=FLAG
PII_CONFIDENCE_THRESHOLD=0.7
```

**Custom entity types:**
```python
PII_ENTITY_TYPES = [
    "NAME", "ADDRESS", "PHONE", "EMAIL", "DATE_TIME",
    "SSN", "BANK_ACCOUNT_NUMBER",
]
# Note: Comprehend detects general PII. For PHI-specific detection
# (MRN, diagnosis codes), combine with custom regex patterns.
```

**Sample input:**
```json
{
  "note_id": "CN-20250515-0042",
  "patient": "Robert Martinez",
  "dob": "March 15, 1958",
  "provider": "Dr. Emily Chen",
  "department": "Cardiology",
  "note": "Patient Robert Martinez (DOB 3/15/1958) presents with chest pain. History of hypertension. Contact wife Maria at (206) 555-0134. Follow-up scheduled January 20, 2025."
}
```

**Output (FLAG mode — text unchanged, metadata added):**
```json
{
  "note_id": "CN-20250515-0042",
  "patient": "Robert Martinez",
  "dob": "March 15, 1958",
  "provider": "Dr. Emily Chen",
  "department": "Cardiology",
  "note": "Patient Robert Martinez (DOB 3/15/1958) presents with chest pain...",
  "pii_flag": true,
  "pii_count": 5,
  "pii_types": ["NAME", "DATE_TIME", "PHONE"],
  "pii_scanned_at": "2025-05-15T01:30:00Z"
}
```

**Compliance mapping:** HIPAA (Health Insurance Portability and Accountability Act)

**OpenSearch query for compliance audit:**
```json
{
  "query": {
    "bool": {
      "must": [
        {"term": {"pii_flag": true}},
        {"terms": {"pii_types": ["NAME", "DATE_TIME"]}}
      ]
    }
  }
}
```

---

## Example 3: Legal — Contract Repository

**Scenario:** A law firm indexes contracts into OpenSearch for clause search. Client names and addresses should be redacted in the search index while preserving the original in a secure vault.

**Configuration:**
```bash
OPENSEARCH_INDEX=contracts-redacted
PII_HANDLING_MODE=REDACT
PII_CONFIDENCE_THRESHOLD=0.85
```

**Custom entity types (narrow scope):**
```python
PII_ENTITY_TYPES = ["NAME", "ADDRESS", "PHONE", "EMAIL", "SSN"]
# Exclude DATE_TIME — dates are important for contract analysis
```

**Dual-index pattern** (store original separately):
```python
from pii_processor import process_document, bulk_index
from os_client import get_client
import copy

client = get_client()
doc = {"title": "Service Agreement", "body": "Between Acme Corp and Jane Doe..."}

# Store original in secure index (access-controlled)
client.index(index="contracts-original", body=doc)

# Store redacted in search index (broad access)
redacted = process_document(copy.deepcopy(doc), mode="REDACT")
client.index(index="contracts-redacted", body=redacted)
```

---

## Example 4: Insurance — Claims Processing

**Scenario:** An insurer processes claims documents. PII must be detected and the document routed differently based on PII type — SSN/financial data goes to a restricted queue, names/addresses are acceptable.

**Configuration:**
```bash
OPENSEARCH_INDEX=claims
PII_HANDLING_MODE=FLAG
```

**Custom routing logic:**
```python
from pii_processor import process_document

SENSITIVE_TYPES = {"SSN", "CREDIT_DEBIT_NUMBER", "BANK_ACCOUNT_NUMBER"}

def route_claim(doc: dict) -> str:
    processed = process_document(doc, mode="FLAG")
    detected_types = set(processed.get("pii_types", []))

    if detected_types & SENSITIVE_TYPES:
        return "restricted"  # Route to restricted queue
    elif processed["pii_flag"]:
        return "standard"    # Has PII but not financial
    else:
        return "open"        # No PII, open access

# Usage
doc = {"claim_id": "CLM-001", "body": "Claimant SSN 123-45-6789..."}
queue = route_claim(doc)
print(f"Route to: {queue}")  # "restricted"
```

---

## Example 5: HR — Resume/CV Screening

**Scenario:** An HR platform indexes resumes for recruiter search. Candidate PII must be redacted to enable blind screening (reduce hiring bias).

**Configuration:**
```bash
OPENSEARCH_INDEX=resumes-blind
PII_HANDLING_MODE=REDACT
PII_CONFIDENCE_THRESHOLD=0.75
```

**Custom entity types:**
```python
PII_ENTITY_TYPES = ["NAME", "EMAIL", "PHONE", "ADDRESS"]
# Keep DATE_TIME (graduation dates are relevant)
# Keep BANK_ACCOUNT_NUMBER excluded (not in resumes)
```

**Sample flow:**
```python
resume = {
    "candidate_id": "anon-uuid-here",
    "text": "Jane Smith | jane.smith@email.com | (555) 123-4567\n"
            "Senior Software Engineer with 8 years experience...\n"
            "Education: MIT, BS Computer Science, 2016\n"
            "Address: 789 Pine St, San Francisco CA 94102"
}

processed = process_document(resume, mode="REDACT")
# Result: "[NAME] | [EMAIL] | [PHONE]\nSenior Software Engineer..."
# Recruiter sees skills and experience, not identity
```

---

## Example 6: Multi-Language Support

**Scenario:** A global company processes documents in multiple languages.

**Configuration per language:**
```bash
# For Spanish documents
COMPREHEND_LANGUAGE=es

# For German documents
COMPREHEND_LANGUAGE=de
```

**Supported languages for PII detection:**
- English (en)
- Spanish (es)
- French (fr)
- German (de)
- Italian (it)
- Portuguese (pt)

**Multi-language pipeline:**
```python
import boto3
from pii_processor import _get_comprehend

def detect_language(text: str) -> str:
    resp = _get_comprehend().detect_dominant_language(Text=text[:300])
    langs = resp.get("Languages", [])
    return langs[0]["LanguageCode"] if langs else "en"

def process_multilingual(doc: dict):
    text = " ".join(v for v in doc.values() if isinstance(v, str) and len(v) > 20)
    lang = detect_language(text)
    # Override language for this document
    import config
    config.COMPREHEND_LANGUAGE = lang
    return process_document(doc)
```

---

## Example 7: EventBridge + S3 Integration (Serverless)

**Scenario:** Documents land in S3 → automatically scanned → indexed to OpenSearch with PII metadata.

**S3 bucket notification (add to existing bucket):**
```bash
aws s3api put-bucket-notification-configuration \
  --bucket your-document-bucket \
  --notification-configuration '{
    "LambdaFunctionConfigurations": [{
      "LambdaFunctionArn": "arn:aws:lambda:us-east-1:123456789012:function:pii-detect-processor",
      "Events": ["s3:ObjectCreated:*"],
      "Filter": {
        "Key": {
          "FilterRules": [
            {"Name": "prefix", "Value": "incoming/"},
            {"Name": "suffix", "Value": ".json"}
          ]
        }
      }
    }]
  }'
```

**Document flow:**
1. Upload: `aws s3 cp claim.json s3://your-bucket/incoming/claim.json`
2. Lambda triggers automatically
3. Document scanned, redacted, indexed to OpenSearch
4. Query OpenSearch for results

---

## Example 8: Compliance Dashboard Query

**Scenario:** Build a compliance dashboard showing PII detection metrics.

**OpenSearch queries for dashboard panels:**

```json
// Total documents by PII status
{
  "size": 0,
  "aggs": {
    "pii_status": {
      "terms": {"field": "pii_flag"}
    }
  }
}

// PII types distribution
{
  "size": 0,
  "aggs": {
    "types": {
      "terms": {"field": "pii_types", "size": 20}
    }
  }
}

// Documents scanned per day
{
  "size": 0,
  "aggs": {
    "daily": {
      "date_histogram": {
        "field": "pii_scanned_at",
        "calendar_interval": "day"
      }
    }
  }
}

// High-risk documents (3+ PII types)
{
  "query": {
    "range": {"pii_count": {"gte": 3}}
  },
  "sort": [{"pii_count": "desc"}],
  "size": 20
}
```
