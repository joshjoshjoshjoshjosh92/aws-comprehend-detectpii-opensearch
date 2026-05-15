# Troubleshooting Guide

A comprehensive guide covering every issue you might hit from first deploy through production operations.

---

## Before You Deploy (Prerequisites)

### "aws: command not found"

**You need:** AWS CLI v2 installed.

```bash
# macOS
brew install awscli

# Linux
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip && sudo ./aws/install

# Verify
aws --version
```

---

### "Unable to locate credentials"

**You need:** AWS credentials configured.

```bash
# Option 1: SSO login
aws sso login --profile your-profile

# Option 2: Configure directly
aws configure
# Enter: Access Key, Secret Key, Region (us-east-1), Output (json)

# Verify
aws sts get-caller-identity
```

---

### "Session Manager Plugin not found"

**You need:** SSM plugin to connect to EC2 instances.

```bash
# macOS
brew install --cask session-manager-plugin

# Linux
curl "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/ubuntu_64bit/session-manager-plugin.deb" -o "session-manager-plugin.deb"
sudo dpkg -i session-manager-plugin.deb

# Verify
session-manager-plugin --version
```

---

### "User is not authorized to perform: cloudformation:CreateStack"

**You need:** Sufficient IAM permissions. The deploying user/role needs:
- `cloudformation:*`
- `ec2:*` (VPC, subnets, security groups, instances)
- `es:*` (OpenSearch)
- `iam:*` (roles, policies, instance profiles)
- `lambda:*` (serverless mode)
- `events:*` (serverless mode)
- `logs:*` (CloudWatch)

**Simplest fix:** Use an IAM user/role with `AdministratorAccess` for the initial deploy. Scope down later.

---

## Deployment Issues

### CloudFormation fails: "Resource limit exceeded"

**Cause:** Account limits for OpenSearch domains (default: 10) or VPCs (default: 5).

**Fix:**
```bash
# Check OpenSearch domains
aws opensearch list-domain-names --region us-east-1

# Check VPCs
aws ec2 describe-vpcs --query 'Vpcs | length(@)' --region us-east-1

# Request increase
aws service-quotas request-service-quota-increase \
  --service-code es --quota-code L-076D529E --desired-value 20
```

---

### CloudFormation fails: "The maximum number of addresses has been reached"

**Cause:** Elastic IP limit reached (default: 5 per region). NAT Gateway needs one.

**Fix:**
```bash
# Check current EIPs
aws ec2 describe-addresses --query 'Addresses | length(@)'

# Release unused ones or request increase
aws service-quotas request-service-quota-increase \
  --service-code ec2 --quota-code L-0263D0A3 --desired-value 10
```

---

### CloudFormation fails: "Role pii-detect-ec2-role already exists"

**Cause:** A previous failed/deleted stack left the IAM role behind.

**Fix:**
```bash
# Delete the orphaned role
aws iam delete-role-policy --role-name pii-detect-ec2-role --policy-name pii-detect-policy
aws iam remove-role-from-instance-profile --instance-profile-name pii-detect-ec2-role --role-name pii-detect-ec2-role 2>/dev/null
aws iam delete-instance-profile --instance-profile-name pii-detect-ec2-role 2>/dev/null
aws iam detach-role-policy --role-name pii-detect-ec2-role --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
aws iam delete-role --role-name pii-detect-ec2-role
```

Then retry the deploy.

---

### CloudFormation stuck in CREATE_IN_PROGRESS (30+ minutes)

**Cause:** OpenSearch domain provisioning takes 10-15 minutes. If it exceeds 30, check for issues.

**Fix:**
```bash
# Check which resource is stuck
aws cloudformation describe-stack-events --stack-name pii-detect \
  --query 'StackEvents[?ResourceStatus==`CREATE_IN_PROGRESS`].[LogicalResourceId,Timestamp]' \
  --output table --region us-east-1

# If it's OpenSearchDomain, just wait (can take up to 20 min)
# If it's something else, check for failures:
aws cloudformation describe-stack-events --stack-name pii-detect \
  --query 'StackEvents[?ResourceStatus==`CREATE_FAILED`].[LogicalResourceId,ResourceStatusReason]' \
  --output table
```

---

### CloudFormation fails: "Encountered unsupported property"

**Cause:** Your AWS CLI or CloudFormation version doesn't support a resource property.

**Fix:** Update AWS CLI:
```bash
pip install --upgrade awscli
# or
brew upgrade awscli
```

---

### CloudFormation DELETE_FAILED (can't delete stack)

**Cause:** OpenSearch domain or VPC has dependencies that prevent deletion.

**Fix:**
```bash
# Force delete with retain on problematic resources
aws cloudformation delete-stack --stack-name pii-detect \
  --retain-resources OpenSearchDomain --region us-east-1

# Then manually delete the OpenSearch domain
aws opensearch delete-domain --domain-name pii-detect-domain --region us-east-1
```

---

## Post-Deploy: Connecting

### "ssm start-session" hangs or times out

**Cause:** EC2 instance hasn't finished booting, or SSM agent isn't running.

**Fix:**
```bash
# Check instance state
aws ec2 describe-instances --instance-ids <id> \
  --query 'Reservations[0].Instances[0].State.Name'

# Check SSM agent status
aws ssm describe-instance-information \
  --filters "Key=InstanceIds,Values=<id>" \
  --query 'InstanceInformationList[0].PingStatus'

# If "Online" but still can't connect, wait 2-3 minutes for UserData to finish
```

---

### Connected via SSM but "/home/ec2-user/pii-detect" doesn't exist

**Cause:** UserData script hasn't finished running yet.

**Fix:**
```bash
# Check if setup completed
cat /home/ec2-user/setup-complete.txt

# If not, check progress
sudo tail -f /var/log/cloud-init-output.log

# If it failed, run manually:
sudo dnf install -y python3-pip git
pip3 install boto3 opensearch-py requests-aws4auth python-dotenv
cd /home/ec2-user
git clone https://github.com/joshjoshjoshjoshjosh92/aws-comprehend-detectpii-opensearch.git pii-detect
```

---

### "OPENSEARCH_ENDPOINT environment variable is required"

**Cause:** The `.env` file is missing or empty.

**Fix:**
```bash
cd /home/ec2-user/pii-detect

# Get endpoint from CloudFormation
ENDPOINT=$(aws cloudformation describe-stacks --stack-name pii-detect \
  --query 'Stacks[0].Outputs[?OutputKey==`OpenSearchEndpoint`].OutputValue' \
  --output text --region us-east-1)

# Write .env
echo "OPENSEARCH_ENDPOINT=$ENDPOINT" > .env
echo "AWS_REGION=us-east-1" >> .env

# Verify
cat .env
python3 -c "from config import OPENSEARCH_ENDPOINT; print(OPENSEARCH_ENDPOINT)"
```

---

## OpenSearch Connection Issues

### "AuthorizationException(403)" — signature mismatch

**Cause:** SigV4 signing is using the wrong region or service name.

**Fix:** Verify your config:
```bash
# Check region matches
echo $AWS_REGION
cat .env | grep REGION

# Test connection directly
python3 -c "
from os_client import get_client
client = get_client()
print(client.info())
"
```

---

### "AuthorizationException(403)" — role not authorized

**Cause:** The IAM role isn't trusted by the OpenSearch domain access policy.

**Fix:**
```bash
# Check what role you're using
aws sts get-caller-identity

# Check OpenSearch access policy
aws opensearch describe-domain --domain-name pii-detect-domain \
  --query 'DomainStatus.AccessPolicies' --output text | python3 -m json.tool
```

The access policy must include your role ARN in the `Principal` field.

---

### "ConnectionTimeout" — can't reach OpenSearch

**Cause:** Network path is blocked between your compute and OpenSearch.

**Checklist:**
```bash
# 1. Are they in the same VPC?
aws ec2 describe-instances --instance-ids <ec2-id> --query 'Reservations[0].Instances[0].VpcId'
aws opensearch describe-domain --domain-name pii-detect-domain --query 'DomainStatus.VPCOptions.VPCId'

# 2. Same subnet or routable?
aws ec2 describe-instances --instance-ids <ec2-id> --query 'Reservations[0].Instances[0].SubnetId'
aws opensearch describe-domain --domain-name pii-detect-domain --query 'DomainStatus.VPCOptions.SubnetIds'

# 3. Security group allows 443?
aws opensearch describe-domain --domain-name pii-detect-domain --query 'DomainStatus.VPCOptions.SecurityGroupIds'
aws ec2 describe-security-groups --group-ids <os-sg-id> --query 'SecurityGroups[0].IpPermissions'
```

---

### "index_not_found_exception"

**Cause:** First run — the index doesn't exist yet.

**Fix:**
```bash
python3 add_more_data.py
# This creates the index with proper mappings and seeds 5 test docs
```

---

## Comprehend Issues

### "ThrottlingException"

**Cause:** Exceeded Comprehend's default 10 TPS limit.

**Fix:** The solution handles this automatically with retry + backoff. If you're seeing persistent throttling:

```bash
# Option 1: Use batch mode (no TPS limit)
python3 batch_detect.py --bucket your-bucket --role-arn your-role-arn

# Option 2: Request limit increase
# Go to Service Quotas → Amazon Comprehend → "Transactions per second for DetectPiiEntities"
```

---

### "TextSizeLimitExceededException"

**Cause:** Document exceeds 100KB. The solution truncates to 99KB automatically, so this shouldn't happen.

**Fix:** If you see this, check that you're using the latest code:
```bash
cd /home/ec2-user/pii-detect && git pull
```

---

### False positives (clean text flagged as PII)

**Cause:** Confidence threshold too low.

**Fix:**
```bash
# Increase threshold (default 0.7, try 0.85 or 0.9)
echo "PII_CONFIDENCE_THRESHOLD=0.9" >> .env
```

---

### False negatives (PII not detected)

**Cause:** Entity type not in configured list, or text too short/ambiguous for Comprehend.

**Fix:**
```python
# Test what Comprehend actually sees (no filters)
import boto3
c = boto3.client("comprehend", region_name="us-east-1")
resp = c.detect_pii_entities(Text="your text here", LanguageCode="en")
for e in resp["Entities"]:
    print(f"  {e['Type']}: score={e['Score']:.2f}, text='{e['BeginOffset']}-{e['EndOffset']}'")
```

If the entity type isn't in your `PII_ENTITY_TYPES` list, add it to `.env` or `config.py`.

---

### "InvalidRequestException: Input text should be UTF-8 encoded"

**Cause:** Document contains non-UTF-8 characters (binary data, corrupted encoding).

**Fix:** Pre-filter your documents:
```python
text = text.encode("utf-8", errors="ignore").decode("utf-8")
```

---

## Lambda Issues (Serverless Mode)

### Lambda times out (300 seconds)

**Cause:** Too many unscanned docs for one invocation.

**Fix:** The Lambda is capped at 10 iterations × BATCH_SIZE docs per invocation. Remaining docs are picked up on the next scheduled run. If you need faster processing:
```bash
# Reduce schedule interval
ScanSchedule="rate(1 minute)"

# Or reduce batch size for faster per-doc processing
SCAN_BATCH_SIZE=10
```

---

### Lambda "Task timed out" on first invocation

**Cause:** VPC Lambda cold start + OpenSearch connection setup can take 15-20 seconds on first call.

**Fix:** This is normal for the first invocation. Subsequent calls within ~15 minutes reuse the warm container. If latency matters:
- Use Provisioned Concurrency
- Or accept the cold start (it only affects the first call)

---

### Lambda can't reach OpenSearch

**Cause:** Lambda security group or subnet misconfigured.

**Checklist:**
1. Lambda is in the private subnet (same as OpenSearch)
2. Lambda SG allows outbound 443
3. OpenSearch SG allows inbound 443 from Lambda SG
4. Private subnet has a route to NAT Gateway (for Comprehend API calls)

```bash
# Check Lambda VPC config
aws lambda get-function-configuration --function-name pii-detect-processor \
  --query 'VpcConfig.{Subnets: SubnetIds, SGs: SecurityGroupIds}'
```

---

### Lambda can't reach Comprehend API

**Cause:** No internet access from the private subnet (NAT Gateway missing or route table wrong).

**Fix:**
```bash
# Check route table for the private subnet
SUBNET_ID=$(aws lambda get-function-configuration --function-name pii-detect-processor \
  --query 'VpcConfig.SubnetIds[0]' --output text)

RT_ID=$(aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=$SUBNET_ID" \
  --query 'RouteTables[0].RouteTableId' --output text)

aws ec2 describe-route-tables --route-table-ids $RT_ID \
  --query 'RouteTables[0].Routes'
# Should show 0.0.0.0/0 → nat-xxxxx
```

---

### "Module not found: opensearchpy" in Lambda

**Cause:** Lambda was deployed with the placeholder code instead of the full package.

**Fix:** Deploy the real handler with dependencies:
```bash
cd /tmp && rm -rf lambda-pkg && mkdir lambda-pkg && cd lambda-pkg
pip install opensearch-py requests-aws4auth -t .
cp /path/to/lambda/handler.py .
zip -r /tmp/lambda-deploy.zip .

aws lambda update-function-code \
  --function-name pii-detect-processor \
  --zip-file fileb:///tmp/lambda-deploy.zip
```

---

## Batch Job Issues

### "AccessDeniedException" on StartPiiEntitiesDetectionJob

**Cause:** EC2/Lambda role needs `iam:PassRole` permission to hand the data access role to Comprehend.

**Fix:** Add to your EC2/Lambda role:
```json
{
  "Effect": "Allow",
  "Action": "iam:PassRole",
  "Resource": "arn:aws:iam::<account>:role/pii-detect-comprehend-data-role"
}
```

---

### Batch job status: FAILED

**Cause:** Usually the Comprehend data access role can't read from S3.

**Fix:**
```bash
# Check job failure reason
aws comprehend describe-pii-entities-detection-job --job-id <job-id> \
  --query 'PiiEntitiesDetectionJobProperties.Message'

# Ensure the data access role has S3 permissions:
aws iam get-role-policy --role-name pii-detect-comprehend-data-role --policy-name s3-access
```

The role needs `s3:GetObject`, `s3:PutObject`, `s3:ListBucket` on your bucket.

---

### Batch job completes but "Updated 0 documents"

**Cause:** Output file parsing didn't match expected format.

**Fix:**
```bash
# Check what Comprehend actually output
aws s3 ls s3://your-bucket/pii-batch-output/ --recursive

# Download and inspect
aws s3 cp s3://your-bucket/pii-batch-output/<path>/<file>.out - | head -5
```

---

## Performance Issues

### Scanning is slow (< 5 docs/second)

**Cause:** Each doc makes 1-2 Comprehend API calls sequentially.

**Fix:**
- This is expected for real-time mode (Comprehend TPS limit)
- For faster processing, use batch mode: `python3 batch_detect.py --bucket ...`
- Or request a TPS increase from AWS

---

### OpenSearch indexing is slow

**Cause:** Using `refresh="wait_for"` forces a sync after each batch.

**Fix:** The solution already uses bulk indexing. If you need more throughput:
```python
# In detect_pii.py, change refresh to False for intermediate batches
bulk_index(client, batch, refresh=False)  # Only refresh on final batch
```

---

## Cleanup Issues

### Stack deletion hangs on OpenSearch domain

**Cause:** OpenSearch domains take 5-10 minutes to delete.

**Fix:** Just wait. If it exceeds 20 minutes:
```bash
# Check status
aws opensearch describe-domain --domain-name pii-detect-domain \
  --query 'DomainStatus.Deleted'

# If stuck, force delete
aws opensearch delete-domain --domain-name pii-detect-domain
```

---

### Stack deletion fails: "VPC has dependencies"

**Cause:** Something outside the stack is using the VPC (e.g., a manually created resource).

**Fix:**
```bash
# Find what's using the VPC
aws ec2 describe-network-interfaces \
  --filters "Name=vpc-id,Values=<vpc-id>" \
  --query 'NetworkInterfaces[].{Id: NetworkInterfaceId, Type: InterfaceType, Description: Description}'
```

Delete the dependent resources, then retry stack deletion.

---

### Lingering costs after deletion

**Check for orphaned resources:**
```bash
# OpenSearch domains
aws opensearch list-domain-names

# NAT Gateways (most expensive orphan)
aws ec2 describe-nat-gateways --filter "Name=state,Values=available" \
  --query 'NatGateways[].{Id: NatGatewayId, VpcId: VpcId}'

# Elastic IPs
aws ec2 describe-addresses --query 'Addresses[?AssociationId==null].{IP: PublicIp, AllocId: AllocationId}'

# CloudWatch Log Groups
aws logs describe-log-groups --log-group-name-prefix /pii-detect \
  --query 'logGroups[].logGroupName'
```

---

## Quick Diagnostic Script

Run this to check the health of your entire deployment:

```bash
#!/bin/bash
echo "=== PII Detect Health Check ==="

echo -e "\n1. AWS Identity:"
aws sts get-caller-identity --output table

echo -e "\n2. Stack Status:"
aws cloudformation describe-stacks --stack-name pii-detect \
  --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "Stack not found"

echo -e "\n3. OpenSearch Domain:"
aws opensearch describe-domain --domain-name pii-detect-domain \
  --query 'DomainStatus.{Endpoint: Endpoint, Processing: Processing, EngineVersion: EngineVersion}' \
  --output table 2>/dev/null || echo "Domain not found"

echo -e "\n4. EC2 Instance:"
aws ec2 describe-instances --filters "Name=tag:Name,Values=pii-detect-processor" "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].{Id: InstanceId, State: State.Name}' \
  --output table 2>/dev/null || echo "No EC2 instance"

echo -e "\n5. Lambda Function:"
aws lambda get-function --function-name pii-detect-processor \
  --query '{State: Configuration.State, Runtime: Configuration.Runtime, Timeout: Configuration.Timeout}' \
  --output table 2>/dev/null || echo "No Lambda function"

echo -e "\n6. SSM Connectivity:"
INSTANCE_ID=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=pii-detect-processor" "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].InstanceId' --output text 2>/dev/null)
if [ "$INSTANCE_ID" != "None" ] && [ -n "$INSTANCE_ID" ]; then
  aws ssm describe-instance-information --filters "Key=InstanceIds,Values=$INSTANCE_ID" \
    --query 'InstanceInformationList[0].PingStatus' --output text
else
  echo "N/A (no EC2 instance)"
fi

echo -e "\n=== Done ==="
```

Save as `health_check.sh` and run anytime you need to diagnose issues.
