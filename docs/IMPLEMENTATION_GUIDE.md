# Implementation Guide

A step-by-step guide to deploying and operating the PII Detection solution in your AWS account.

---

## Prerequisites

- AWS account with admin access (or permissions to create VPC, OpenSearch, EC2/Lambda, IAM)
- AWS CLI v2 installed and configured
- Python 3.8+ (for local development only)
- Session Manager Plugin (for EC2 mode SSM access)

---

## Step 1: Choose Your Deployment Mode

| Mode | Best For | Deploy Command |
|------|----------|----------------|
| **EC2** | Demos, development, always-on | `DeploymentMode=ec2` |
| **Serverless** | Production, variable volume | `DeploymentMode=serverless` |

---

## Step 2: Deploy the Stack

### Option A: EC2 Mode (Default)

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name pii-detect \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

### Option B: Serverless Mode

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name pii-detect \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1 \
  --parameter-overrides DeploymentMode=serverless ScanSchedule="rate(5 minutes)"
```

### Option C: Console Deploy

1. Open [CloudFormation Console](https://console.aws.amazon.com/cloudformation)
2. Click **Create Stack** → **With new resources**
3. Upload `template.yaml`
4. Fill in parameters (defaults work for most cases)
5. Acknowledge IAM capabilities
6. Click **Create Stack**

**Deployment takes ~15 minutes** (OpenSearch domain provisioning is the bottleneck).

---

## Step 3: Verify Deployment

```bash
# Check stack status
aws cloudformation describe-stacks --stack-name pii-detect \
  --query 'Stacks[0].StackStatus' --output text

# Get outputs
aws cloudformation describe-stacks --stack-name pii-detect \
  --query 'Stacks[0].Outputs' --output table
```

---

## Step 4: Run the Demo (EC2 Mode)

### Connect to the instance:

```bash
INSTANCE_ID=$(aws cloudformation describe-stacks --stack-name pii-detect \
  --query 'Stacks[0].Outputs[?OutputKey==`EC2InstanceId`].OutputValue' --output text)

aws ssm start-session --target $INSTANCE_ID --region us-east-1
```

### Run the end-to-end demo:

```bash
cd /home/ec2-user/pii-detect
python3 run_demo.py
```

Expected output:
```
=== Step 0: Health Check ===
Cluster: ..., Version: 2.11

=== Step 2: Seed Test Data ===
Indexing 5 test documents...

=== Step 4: Run Comprehend PII Detection ===
Found 5 unscanned document(s). Scanning...
  [1] PII id=... types=['SSN', 'ADDRESS', 'PHONE', 'NAME', 'EMAIL']
  [2] PII id=... types=['ADDRESS', 'DATE_TIME', 'NAME', 'BANK_ACCOUNT_NUMBER']
  [3] ok  id=... types=[]
  ...

=== Step 6: PII Type Breakdown ===
  NAME: 3
  ADDRESS: 2
  ...
```

---

## Step 5: Process Your Own Documents

### From a JSON file:

```bash
# Single document
echo '{"title": "Test", "body": "Contact John Smith at john@example.com"}' > doc.json
python3 pii_processor.py --input doc.json --mode REDACT
```

### Scan existing OpenSearch documents:

```bash
# Scan all unscanned docs (paginated)
python3 detect_pii.py

# Scan with batch size of 100, cap at 500 docs
python3 detect_pii.py 100 500
```

### Large-scale batch processing:

```bash
# Create an S3 bucket for batch I/O
aws s3 mb s3://my-pii-batch-bucket

# Run async Comprehend job (50% cheaper)
python3 batch_detect.py \
  --bucket my-pii-batch-bucket \
  --role-arn arn:aws:iam::123456789012:role/ComprehendDataAccessRole \
  --max-docs 50000
```

---

## Step 6: Verify Results

### View flagged documents:

```bash
python3 view_flagged.py --limit 10
```

### Query OpenSearch directly:

```bash
# Count by PII status
curl -s "https://$ENDPOINT/pii-test/_search" -H 'Content-Type: application/json' -d '{
  "size": 0,
  "aggs": {
    "pii_status": { "terms": { "field": "pii_flag" } }
  }
}'
```

---

## Step 7: Customize for Your Use Case

### Change PII entity types:

Edit `.env` or set environment variable:
```bash
# Only detect financial PII
PII_ENTITY_TYPES=SSN,CREDIT_DEBIT_NUMBER,BANK_ACCOUNT_NUMBER
```

### Change handling mode:

```bash
# Flag only (don't redact, just add metadata)
PII_HANDLING_MODE=FLAG
```

### Adjust confidence threshold:

```bash
# Higher threshold = fewer false positives
PII_CONFIDENCE_THRESHOLD=0.9
```

---

## Step 8: Integrate with Your Pipeline

### Option A: S3 Event Trigger (Serverless Mode)

Add an S3 event notification to trigger the Lambda when new documents land:

```bash
aws s3api put-bucket-notification-configuration \
  --bucket your-document-bucket \
  --notification-configuration '{
    "LambdaFunctionConfigurations": [{
      "LambdaFunctionArn": "arn:aws:lambda:us-east-1:123456789012:function:pii-detect-processor",
      "Events": ["s3:ObjectCreated:*"],
      "Filter": {"Key": {"FilterRules": [{"Name": "suffix", "Value": ".json"}]}}
    }]
  }'
```

### Option B: Direct API Integration

Invoke the Lambda directly from your application:

```python
import boto3, json

lambda_client = boto3.client("lambda")
response = lambda_client.invoke(
    FunctionName="pii-detect-processor",
    Payload=json.dumps({"document": {"title": "Test", "body": "SSN 123-45-6789"}})
)
result = json.loads(response["Payload"].read())
# result: {"pii_flag": true, "pii_types": ["SSN"], "pii_count": 1}
```

---

## Monitoring & Observability

### CloudWatch Logs:

- `/pii-detect/audit` — PII detection audit trail (90-day retention)
- `/pii-detect/vpc-flow-logs` — Network traffic logs (30-day retention)
- `/aws/lambda/pii-detect-processor` — Lambda execution logs (serverless mode)

### Key metrics to monitor:

- Documents scanned per hour
- PII detection rate (% flagged)
- Comprehend API errors / throttles
- Lambda duration and errors (serverless mode)

---

## Cleanup

Remove all resources:

```bash
aws cloudformation delete-stack --stack-name pii-detect --region us-east-1
aws cloudformation wait stack-delete-complete --stack-name pii-detect --region us-east-1
```

This deletes everything: VPC, OpenSearch domain, EC2/Lambda, IAM roles, log groups. No lingering costs.

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| `OPENSEARCH_ENDPOINT not set` | Missing .env file | `cp .env.example .env` and set endpoint |
| `AuthorizationException` | IAM role can't access OpenSearch | Check access policy matches role ARN |
| `ThrottlingException` | Comprehend rate limit (10 TPS default) | Script auto-retries; or request limit increase |
| Lambda timeout | Too many docs in one invocation | Reduce `SCAN_BATCH_SIZE` env var |
| OpenSearch `index_not_found` | First run, index doesn't exist | Run `python3 add_more_data.py` to create it |

---

## Cost Management

### Monitor spend:

```bash
# Check Comprehend costs (last 7 days)
aws ce get-cost-and-usage \
  --time-period Start=$(date -d '7 days ago' +%Y-%m-%d),End=$(date +%Y-%m-%d) \
  --granularity DAILY \
  --filter '{"Dimensions":{"Key":"SERVICE","Values":["Amazon Comprehend"]}}' \
  --metrics BlendedCost
```

### Cost guardrails:

- Set `max_docs` parameter in `detect_pii.py` to cap per-run spend
- Use EventBridge schedule to control scan frequency
- Set AWS Budget alerts on Comprehend service
