# Quick Start Guide

Deploy the PII Detection solution in your AWS account in under 20 minutes.

---

## Pre-Flight Checklist

Run these before deploying. If any fail, see the fix below.

```bash
# 1. AWS CLI installed?
aws --version
# Need: 2.x. If missing: brew install awscli (macOS) or https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html

# 2. Authenticated?
aws sts get-caller-identity
# Need: valid output with Account and Arn. If "expired" or "unable to locate credentials": aws sso login or aws configure

# 3. Correct region?
aws configure get region
# Need: us-east-1 (or your target region). If wrong: export AWS_REGION=us-east-1

# 4. Session Manager plugin? (needed for EC2 mode)
session-manager-plugin --version
# Need: any version. If missing: brew install --cask session-manager-plugin (macOS)

# 5. Sufficient permissions?
aws iam get-user 2>/dev/null || aws sts get-caller-identity
# Need: Admin access or equivalent. If not: ask your admin for CloudFormation + EC2 + OpenSearch + IAM + Lambda permissions
```

**All 5 pass? You're ready to deploy.**

---

## Option 1: One-Click Deploy (CLI)

### EC2 Mode (recommended for first-time / demos)

```bash
# Clone the repo
git clone https://github.com/joshjoshjoshjoshjosh92/aws-comprehend-detectpii-opensearch.git
cd aws-comprehend-detectpii-opensearch

# Deploy (takes ~15 minutes)
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name pii-detect \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1

# Wait for it (optional — deploy command already waits)
aws cloudformation wait stack-create-complete --stack-name pii-detect --region us-east-1
```

### Serverless Mode (recommended for production)

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name pii-detect \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1 \
  --parameter-overrides DeploymentMode=serverless ScanSchedule="rate(5 minutes)"
```

---

## Option 2: Console Deploy

1. Open [CloudFormation Console](https://console.aws.amazon.com/cloudformation/home#/stacks/create)
2. Select **Upload a template file** → choose `template.yaml`
3. Stack name: `pii-detect`
4. Parameters: leave defaults (or set `DeploymentMode=serverless`)
5. Check **"I acknowledge that AWS CloudFormation might create IAM resources with custom names"**
6. Click **Create stack**
7. Wait ~15 minutes for `CREATE_COMPLETE`

---

## After Deployment

### EC2 Mode: Connect and Run Demo

```bash
# Get the instance ID
INSTANCE_ID=$(aws cloudformation describe-stacks --stack-name pii-detect \
  --query 'Stacks[0].Outputs[?OutputKey==`EC2InstanceId`].OutputValue' --output text)

# Connect
aws ssm start-session --target $INSTANCE_ID --region us-east-1

# On the instance — run the demo
cd /home/ec2-user/pii-detect
python3 run_demo.py
```

**Expected output:**
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
  [4] PII id=... types=['PHONE', 'DATE_TIME', 'CREDIT_DEBIT_NUMBER', 'NAME']
  [5] ok  id=... types=[]

=== Step 6: PII Type Breakdown ===
  NAME: 3
  PHONE: 2
  ADDRESS: 2
  ...

=== Done ===
```

### Serverless Mode: Test the Lambda

```bash
# Get Lambda ARN
LAMBDA_ARN=$(aws cloudformation describe-stacks --stack-name pii-detect \
  --query 'Stacks[0].Outputs[?OutputKey==`LambdaFunctionArn`].OutputValue' --output text)

# NOTE: You need to deploy the full handler code first (the CFN deploys a placeholder)
cd lambda
zip /tmp/lambda-deploy.zip handler.py
pip install opensearch-py requests-aws4auth -t /tmp/lambda-pkg
cd /tmp/lambda-pkg && zip -r /tmp/lambda-deploy.zip . && cd -

aws lambda update-function-code \
  --function-name pii-detect-processor \
  --zip-file fileb:///tmp/lambda-deploy.zip

# Test with a document
echo '{"document": {"title": "Test", "body": "Contact John Smith at john@example.com, SSN 123-45-6789"}, "index": false}' > /tmp/test-payload.json

aws lambda invoke \
  --function-name pii-detect-processor \
  --cli-binary-format raw-in-base64-out \
  --payload file:///tmp/test-payload.json \
  /tmp/response.json && cat /tmp/response.json
```

**Expected output:**
```json
{"pii_flag": true, "pii_types": ["NAME", "EMAIL", "SSN"], "pii_count": 3}
```

---

## Option 3: Bring Your Own Infrastructure

Already have OpenSearch + EC2? Skip the CloudFormation:

```bash
git clone https://github.com/joshjoshjoshjoshjosh92/aws-comprehend-detectpii-opensearch.git
cd aws-comprehend-detectpii-opensearch
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:
```bash
OPENSEARCH_ENDPOINT=vpc-your-domain.us-east-1.es.amazonaws.com
AWS_REGION=us-east-1
```

Run:
```bash
python3 run_demo.py
```

**Requirements:**
- EC2 instance in the same VPC/subnet as OpenSearch
- IAM role with `comprehend:DetectPiiEntities`, `comprehend:ContainsPiiEntities`, `es:ESHttpPost`, `es:ESHttpPut`, `es:ESHttpGet`
- Security group allowing EC2 → OpenSearch on port 443
- Python 3.8+

---

## Common Issues During Deploy

| Symptom | Cause | Fix |
|---------|-------|-----|
| Stack fails immediately | Missing `--capabilities CAPABILITY_NAMED_IAM` | Add the flag |
| Stack fails: "role already exists" | Previous failed deploy left orphaned resources | Delete the role manually (see Troubleshooting) |
| Stack fails: "limit exceeded" | Too many VPCs or OpenSearch domains | Delete unused ones or request increase |
| Stack takes 30+ minutes | OpenSearch provisioning is slow | Normal up to 20 min; check events if >30 |
| SSM can't connect | Instance still booting | Wait 3-5 min after stack completes |
| "pii-detect" folder missing on EC2 | UserData still running | Check `/var/log/cloud-init-output.log` |
| "OPENSEARCH_ENDPOINT required" | .env file missing | See "After Deployment" section above |

For detailed troubleshooting, see [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

---

## Cleanup

Remove everything — zero lingering costs:

```bash
aws cloudformation delete-stack --stack-name pii-detect --region us-east-1

# Verify deletion (takes ~10 minutes for OpenSearch)
aws cloudformation wait stack-delete-complete --stack-name pii-detect --region us-east-1
```

---

## What's Next?

After the demo works:

1. **Process your own documents:** `python3 pii_processor.py --input your-docs.json`
2. **Scan at scale:** `python3 detect_pii.py 100` (batch size 100, paginate all)
3. **Bulk backfill:** `python3 batch_detect.py --bucket your-bucket --role-arn your-role`
4. **Customize PII types:** Edit `.env` → `PII_ENTITY_TYPES=NAME,SSN,EMAIL`
5. **Switch to serverless:** Redeploy with `DeploymentMode=serverless`

See [docs/EXAMPLES.md](docs/EXAMPLES.md) for industry-specific customization patterns.
