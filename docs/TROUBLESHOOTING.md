# Troubleshooting Guide

---

## Deployment Issues

### CloudFormation stack fails with "Resource limit exceeded"

**Cause:** Account has reached the limit for OpenSearch domains or VPCs.

**Fix:**
```bash
# Check current OpenSearch domains
aws opensearch list-domain-names --region us-east-1

# Check VPC count
aws ec2 describe-vpcs --query 'Vpcs | length(@)' --region us-east-1
```
Delete unused resources or request a limit increase via Service Quotas.

---

### CloudFormation stack stuck in CREATE_IN_PROGRESS for 30+ minutes

**Cause:** OpenSearch domain provisioning takes 10-15 minutes. If it exceeds 30 minutes, there may be a capacity issue.

**Fix:** Check CloudFormation events:
```bash
aws cloudformation describe-stack-events --stack-name pii-detect \
  --query 'StackEvents[?ResourceStatus==`CREATE_FAILED`].[LogicalResourceId,ResourceStatusReason]' \
  --output table
```

---

### EC2 instance UserData fails (setup-complete.txt not created)

**Cause:** Instance can't reach the internet (NAT Gateway issue) or git clone failed.

**Fix:**
```bash
# Connect via SSM
aws ssm start-session --target <instance-id>

# Check UserData log
sudo cat /var/log/cloud-init-output.log | tail -50
```

---

## Connection Issues

### `OPENSEARCH_ENDPOINT environment variable is required`

**Cause:** The `.env` file is missing or doesn't have the endpoint set.

**Fix:**
```bash
# On EC2 instance
cd /home/ec2-user/pii-detect
cat .env  # Should show OPENSEARCH_ENDPOINT=...

# If missing, get it from CloudFormation
aws cloudformation describe-stacks --stack-name pii-detect \
  --query 'Stacks[0].Outputs[?OutputKey==`OpenSearchEndpoint`].OutputValue' --output text
```

---

### `AuthorizationException(403)` when connecting to OpenSearch

**Cause:** IAM role doesn't have permission, or the OpenSearch access policy doesn't trust the role.

**Fix:**
1. Verify the EC2/Lambda role ARN matches what's in the OpenSearch access policy
2. Check that the request is being signed with SigV4:
```python
from os_client import get_client
client = get_client()
print(client.info())  # If this works, auth is fine
```

---

### `ConnectionTimeout` to OpenSearch

**Cause:** Network path is blocked. EC2/Lambda can't reach the OpenSearch VPC endpoint.

**Fix:**
1. Verify EC2/Lambda is in the same VPC and subnet as OpenSearch
2. Check security groups:
```bash
# OpenSearch SG must allow inbound 443 from EC2/Lambda SG
aws ec2 describe-security-groups --group-ids <opensearch-sg-id> \
  --query 'SecurityGroups[0].IpPermissions'
```

---

## Comprehend Issues

### `ThrottlingException` from Comprehend

**Cause:** Exceeded the default 10 transactions per second (TPS) limit.

**Fix:**
- The solution auto-retries with exponential backoff (built into `detect_pii.py`)
- For sustained high throughput, request a limit increase:
```bash
aws service-quotas request-service-quota-increase \
  --service-code comprehend \
  --quota-code L-EXAMPLE \
  --desired-value 50
```
- Or use `batch_detect.py` for large volumes (no TPS limit on async jobs)

---

### `TextSizeLimitExceededException`

**Cause:** Document text exceeds Comprehend's 100KB per-call limit.

**Fix:** The solution automatically truncates to 99,000 characters. If you're seeing this error, check that the truncation is being applied:
```python
text = text[:99_000]  # This should be in detect_pii() and contains_pii()
```

---

### Comprehend detects PII but confidence is low (many false positives)

**Cause:** Default confidence threshold is 0.7 which may be too permissive.

**Fix:** Increase the threshold in `.env`:
```bash
PII_CONFIDENCE_THRESHOLD=0.9
```

---

### Comprehend misses PII that should be detected

**Cause:** The entity type isn't in the configured `PII_ENTITY_TYPES` list, or the text is too short/ambiguous.

**Fix:**
1. Check which types are configured in `config.py`
2. Test the specific text directly:
```python
import boto3
client = boto3.client("comprehend", region_name="us-east-1")
resp = client.detect_pii_entities(Text="your text here", LanguageCode="en")
print(resp["Entities"])  # See ALL detected entities regardless of filter
```

---

## OpenSearch Issues

### `index_not_found_exception`

**Cause:** The index hasn't been created yet (first run).

**Fix:**
```bash
python3 add_more_data.py  # Creates the index with proper mappings + seeds data
```

---

### Documents indexed but `pii_flag` field not appearing

**Cause:** Documents were indexed before the PII scan ran.

**Fix:**
```bash
python3 detect_pii.py  # Scans all docs missing pii_flag
```

---

### Bulk indexing errors (some docs rejected)

**Cause:** Mapping conflict — a field type changed between documents.

**Fix:** Check the bulk response for errors:
```python
from os_client import get_client
client = get_client()
resp = client.search(index="pii-test", body={"query": {"match_all": {}}}, size=1)
print(resp)  # Verify index is accessible
```

---

## Lambda Issues (Serverless Mode)

### Lambda times out after 300 seconds

**Cause:** Too many documents to process in a single invocation.

**Fix:** Reduce batch size:
```bash
# In CloudFormation or Lambda environment variables
SCAN_BATCH_SIZE=10
```

---

### Lambda can't reach OpenSearch (timeout in VPC)

**Cause:** Lambda is in a subnet without a NAT Gateway route, or the security group doesn't allow outbound 443.

**Fix:**
1. Verify Lambda is in the private subnet with NAT Gateway route
2. Verify Lambda SG allows outbound 443
3. Verify OpenSearch SG allows inbound 443 from Lambda SG

---

### Lambda cold start is slow (10+ seconds)

**Cause:** VPC-attached Lambdas have longer cold starts due to ENI provisioning.

**Fix:** This is expected for VPC Lambdas. For latency-sensitive use cases:
- Enable Provisioned Concurrency (adds cost)
- Or use the EC2 mode for consistent latency

---

## Batch Job Issues

### `StartPiiEntitiesDetectionJob` returns AccessDenied

**Cause:** The data access role doesn't have S3 read/write permissions for the specified bucket.

**Fix:** The role needs:
```json
{
  "Effect": "Allow",
  "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
  "Resource": ["arn:aws:s3:::your-bucket", "arn:aws:s3:::your-bucket/*"]
}
```

---

### Batch job completes but no results imported

**Cause:** Output file format doesn't match expected parsing.

**Fix:** Check the raw output:
```bash
aws s3 ls s3://your-bucket/pii-batch-output/ --recursive
aws s3 cp s3://your-bucket/pii-batch-output/<file>.out - | head -5
```

---

## General Debugging

### Enable verbose logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Test individual components in isolation

```python
# Test Comprehend
from pii_processor import contains_pii, detect_pii
print(contains_pii("John Smith lives at 123 Main St"))
print(detect_pii("SSN: 123-45-6789"))

# Test OpenSearch
from os_client import get_client
client = get_client()
print(client.info())
print(client.count(index="pii-test", body={"query": {"match_all": {}}}))
```

### Check current scan status

```python
from os_client import get_client
from config import OPENSEARCH_INDEX
c = get_client()
total = c.count(index=OPENSEARCH_INDEX, body={"query": {"match_all": {}}})["count"]
scanned = c.count(index=OPENSEARCH_INDEX, body={"query": {"exists": {"field": "pii_flag"}}})["count"]
print(f"Total: {total}, Scanned: {scanned}, Remaining: {total - scanned}")
```
