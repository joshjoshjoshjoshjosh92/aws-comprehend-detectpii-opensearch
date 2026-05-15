# Quick Start Guide

## Option 1: One-Click Deploy (Recommended)

Click the button below to deploy the full stack in your AWS account:

[![Launch Stack](https://s3.amazonaws.com/cloudformation-examples/cloudformation-launch-stack.png)](https://console.aws.amazon.com/cloudformation/home#/stacks/new?stackName=pii-detect&templateURL=https://your-bucket.s3.amazonaws.com/template.yaml)

> **Note:** You'll need to host `template.yaml` in an S3 bucket first, or upload it directly in the CloudFormation console.

### What gets deployed:
- VPC with private/public subnets and NAT gateway
- Amazon OpenSearch Service domain (single-node, `t3.small.search`)
- EC2 instance with IAM role (Comprehend + OpenSearch permissions)
- Security groups (EC2 → OpenSearch on port 443 only)
- SSM Session Manager access (no SSH key required)

### After deployment (~15 minutes):

1. Go to **CloudFormation → Outputs** tab
2. Copy the `SSMConnectCommand` value
3. Run it in your terminal:

```bash
aws ssm start-session --target i-xxxxxxxxx --region us-east-1
```

4. On the instance:

```bash
cd /home/ec2-user/pii-detect
python3 run_demo.py
```

That's it. You'll see the full pipeline run: seed data → detect PII → view results.

---

## Option 2: Deploy via CLI

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name pii-detect \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

Wait for completion:

```bash
aws cloudformation wait stack-create-complete --stack-name pii-detect --region us-east-1
```

Then connect:

```bash
INSTANCE_ID=$(aws cloudformation describe-stacks --stack-name pii-detect \
  --query 'Stacks[0].Outputs[?OutputKey==`EC2InstanceId`].OutputValue' --output text)
aws ssm start-session --target $INSTANCE_ID --region us-east-1
```

---

## Option 3: Bring Your Own Infrastructure

If you already have an OpenSearch domain and EC2 instance:

```bash
git clone https://github.com/joshjoshjoshjoshjosh92/aws-comprehend-detectpii-opensearch.git
cd aws-comprehend-detectpii-opensearch
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your OpenSearch endpoint
python3 run_demo.py
```

**Requirements:**
- EC2 instance in the same VPC as your OpenSearch domain
- IAM role with `comprehend:DetectPiiEntities`, `comprehend:ContainsPiiEntities`, and `es:ESHttp*` permissions
- Security group allowing EC2 → OpenSearch on port 443

---

## Cleanup

```bash
aws cloudformation delete-stack --stack-name pii-detect --region us-east-1
```

This removes all resources. No lingering costs.
