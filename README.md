# AWS Cost Alerting System

> **Automated daily cost reporting with budget alerts and automated remediation for AWS infrastructure.**

[![Terraform](https://img.shields.io/badge/terraform-%235835CC.svg?style=flat&logo=terraform&logoColor=white)](https://www.terraform.io/)
[![AWS](https://img.shields.io/badge/AWS-%23FF9900.svg?style=flat&logo=amazon-aws&logoColor=white)](https://aws.amazon.com/)
[![Python](https://img.shields.io/badge/python-3.11+-3670A0?style=flat&logo=python&logoColor=ffdd54)](https://www.python.org/)

## 📋 Table of Contents

- [What is This?](#what-is-this)
- [Features](#features)
- [Architecture Overview](#architecture-overview)
- [Prerequisites](#prerequisites)
- [Quick Start Guide](#quick-start-guide)
- [Configuration](#configuration)
- [How It Works](#how-it-works)
- [Cost Breakdown](#cost-breakdown)
- [Monitoring & Alerts](#monitoring--alerts)
- [Security](#security)
- [Troubleshooting](#troubleshooting)
- [Terraform Infrastructure Explained](#terraform-infrastructure-explained)

## What is This?

This is a **production-ready AWS cost monitoring and alerting system** that:

- 📧 **Sends you daily email reports** with your AWS spending breakdown
- 💰 **Tracks your monthly budget** and alerts you at 80% and 100%
- 🛑 **Automatically stops EC2 instances** when you exceed your budget (optional, safe)
- 📊 **Archives all reports** to S3 for historical analysis
- 🔔 **Monitors itself** with CloudWatch alarms and OpsCenter integration

**Perfect for:**
- Individual developers managing AWS costs
- Small teams wanting cost visibility
- Anyone who wants automated cost control

**Cost:** ~$0.02/month (yes, really!)

## Features

### 📧 Daily Cost Reports
- **Automated emails** at 8:00 PM PT (configurable)
- **Yesterday's costs** broken down by AWS service
- **Month-to-date** spending summary
- **Usage type analysis** to identify cost drivers
- **S3 archive** of JSON/CSV reports for historical analysis

### 💰 Budget Management
- **Monthly budget** with configurable limit
- **Two alert thresholds**: 80% (warning) and 100% (critical)
- **Email notifications** when thresholds are exceeded
- **SNS integration** for custom alerting

### 🛑 Automated Remediation (Optional)
- **Stops EC2 instances** tagged `AutoStop=true` when budget is exceeded
- **Safe by design**: Only stops instances you explicitly tag
- **SSM Automation** with proper IAM scoping
- **No accidental shutdowns**: Requires explicit tagging

### 📊 Monitoring & Observability
- **CloudWatch alarms** for Lambda errors
- **Custom metrics** for report generation tracking
- **Dead Letter Queue** for failed invocations
- **OpsCenter integration** for incident management

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Daily Cost Reporting Flow                 │
└─────────────────────────────────────────────────────────────┘

EventBridge Scheduler (8 PM PT daily)
    ↓
Lambda Function (Cost Reporter)
    ├─→ AWS Cost Explorer API (queries costs)
    ├─→ S3 Bucket (archives JSON/CSV reports)
    └─→ SES (sends email report)

┌─────────────────────────────────────────────────────────────┐
│              Budget Alert & Remediation Flow                 │
└─────────────────────────────────────────────────────────────┘

AWS Budget Threshold Exceeded (80% or 100%)
    ↓
SNS Topic (budget alerts)
    ├─→ Email notification (to your inbox)
    └─→ Lambda Function (Remediation)
            ↓
        SSM Automation Document
            ↓
        Stop EC2 Instances (only those tagged AutoStop=true)
```

## Prerequisites

Before you begin, make sure you have:

1. **AWS Account** with appropriate permissions
2. **AWS CLI** installed and configured
   ```bash
   aws --version  # Should show AWS CLI v2+
   aws configure  # Set up your credentials
   ```
3. **Terraform** >= 1.6.0 installed
   ```bash
   terraform version  # Should show 1.6.0 or higher
   ```
4. **Email Address** that you can access (for SES verification)

### Required IAM Permissions

Your AWS user/role needs permissions to create:
- Lambda functions
- S3 buckets
- SES identities
- EventBridge Scheduler
- SSM documents and parameters
- CloudWatch alarms
- IAM roles and policies
- SNS topics
- AWS Budgets

**Quick Setup:** Attach the `terraform-policy.json` provided in this repo to your IAM user, or use AWS managed policies with appropriate scoping.

## Quick Start Guide

### Step 1: Clone and Navigate

```bash
git clone https://github.com/alexlux58/AWS-ALERTING.git
cd AWS-ALERTING
```

### Step 2: Configure Your Settings

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your values:

```hcl
# Required: Your email addresses
report_to   = "your-email@example.com"
report_from = "your-email@example.com"

# Optional: Adjust budget limit
budget_limit_amount = "100"  # Monthly budget in USD

# Optional: Change schedule time
schedule_timezone = "America/New_York"
schedule_cron    = "cron(0 18 * * ? *)"  # 6:00 PM ET
```

**Important:** The `report_from` email must be one you can access - you'll need to verify it!

### Step 3: Deploy Infrastructure

```bash
# Initialize Terraform
terraform init

# Review what will be created
terraform plan

# Deploy (type 'yes' when prompted)
terraform apply
```

This will create:
- ✅ Lambda functions (cost reporter & remediation)
- ✅ S3 bucket for report archives
- ✅ EventBridge Scheduler (daily trigger)
- ✅ SES email identities
- ✅ CloudWatch alarms
- ✅ AWS Budget
- ✅ SSM Automation document

**Deployment takes ~2-3 minutes.**

### Step 4: Verify Email Identities ⚠️ CRITICAL

**This step is required!** Without it, emails won't be sent.

1. **Check your email inbox** for verification emails from AWS SES
2. **Click the verification links** for:
   - `report_from` email (required)
   - `report_to` email (if `ses_sandbox_mode = true`)

**How to check if verified:**
```bash
aws ses get-identity-verification-attributes \
  --identities your-email@example.com
```

Look for `"VerificationStatus": "Success"`

### Step 5: Test the System

Manually trigger the Lambda to test:

```bash
aws lambda invoke \
  --function-name cost-alerting-reporter \
  --region us-east-1 \
  --payload '{}' \
  /tmp/cost-report.json && cat /tmp/cost-report.json
```

**Expected output:**
```json
{
  "ok": true,
  "date": "2025-01-15",
  "daily_total": 12.34,
  "mtd_total": 234.56
}
```

**Check your email** - you should receive a cost report!

**Check S3 archive:**
```bash
aws s3 ls s3://$(terraform output -raw archive_bucket)/reports/ --recursive
```

### Step 5.5: Verify Everything is Working ✅

After your first successful test, verify all components:

**1. Check Email Delivery in Logs:**
```bash
aws logs tail /aws/lambda/cost-alerting-reporter \
  --region us-east-1 \
  --since 10m | grep -i "email sent"
```

**Expected output:**
```
Email sent successfully to your-email@example.com - SES MessageId: 0100019b2fb8da71-...
```

**2. Verify S3 Archive Files:**
```bash
# List all report files (replace with your bucket name)
aws s3 ls s3://cost-alerting-{account-id}-us-east-1/reports/2025/12/16/ --recursive
```

**Expected files:**
- `daily_by_service.csv`
- `daily_by_service.json`
- `daily_drivers_usage_type.csv`
- `daily_drivers_usage_type.json`
- `mtd_by_service.csv`
- `mtd_by_service.json`

**3. Check Daily Schedule Status:**
```bash
aws scheduler get-schedule \
  --name cost-alerting-daily-8pm \
  --group-name default \
  --region us-east-1 \
  --query 'State'
```

**Expected output:** `"ENABLED"`

**4. View Lambda Response:**
```bash
cat /tmp/cost-report.json
```

**Expected output:**
```json
{
  "ok": true,
  "date": "2025-12-16",
  "daily_total": 0.42,
  "mtd_total": 29.42
}
```

**5. Check CloudWatch Metrics (if enabled):**
```bash
aws cloudwatch get-metric-statistics \
  --namespace cost-alerting \
  --metric-name ReportGenerated \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Sum \
  --region us-east-1
```

**All checks passing?** 🎉 Your system is fully operational and will send daily reports automatically!

### Step 6: Set Up Remediation (Optional)

If you want automatic EC2 instance stopping when budget is exceeded:

1. **Tag instances** you want to auto-stop:
   ```bash
   aws ec2 create-tags \
     --resources i-0123456789abcdef0 \
     --tags Key=AutoStop,Value=true
   ```

2. **Only tagged instances** will be stopped - this is safe!

3. **Test remediation** (optional):
   ```bash
   aws lambda invoke \
     --function-name cost-alerting-remediation \
     --region us-east-1 \
     --payload '{}' \
     /tmp/remediate.json && cat /tmp/remediate.json
   ```

## Configuration

### Terraform Variables

All configuration is done via `terraform.tfvars`. Key variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `report_to` | Email to receive reports | **Required** |
| `report_from` | Email to send from | **Required** |
| `budget_limit_amount` | Monthly budget in USD | `"50"` |
| `schedule_cron` | Cron expression for schedule | `"cron(0 20 * * ? *)"` (8 PM) |
| `schedule_timezone` | Timezone (handles DST) | `"America/Los_Angeles"` |
| `top_n_services` | Number of top services in report | `10` |
| `include_mtd` | Include month-to-date breakdown | `true` |
| `include_drivers` | Include usage type drivers | `true` |
| `ses_sandbox_mode` | SES sandbox mode (verify recipient) | `true` |

**See `infra/terraform.tfvars.example` for all options.**

### Runtime Configuration (SSM Parameters)

Some settings can be changed at runtime without redeploying:

```bash
# Change number of top services in report
aws ssm put-parameter \
  --name "/cost-alerting/top_n_services" \
  --type "String" \
  --value "15" \
  --overwrite

# Disable month-to-date in reports
aws ssm put-parameter \
  --name "/cost-alerting/include_mtd" \
  --type "String" \
  --value "false" \
  --overwrite
```

Available parameters:
- `/cost-alerting/report_to`
- `/cost-alerting/report_from`
- `/cost-alerting/archive_bucket`
- `/cost-alerting/top_n_services`
- `/cost-alerting/include_mtd`
- `/cost-alerting/include_drivers`

## How It Works

### Daily Cost Reporting

1. **EventBridge Scheduler** triggers at 8:00 PM PT (configurable)
2. **Lambda function** queries AWS Cost Explorer API for:
   - Yesterday's costs by service
   - Month-to-date costs
   - Usage type drivers
3. **Reports are generated** in JSON and CSV formats
4. **Reports are archived** to S3 with date-based organization:
   ```
   s3://bucket-name/reports/2025/01/15/
     ├── daily_by_service.json
     ├── daily_by_service.csv
     ├── mtd_by_service.json
     ├── mtd_by_service.csv
     └── daily_drivers_usage_type.json
   ```
5. **Email is sent** via SES with HTML-formatted report

### Budget Alerts & Remediation

1. **AWS Budget** monitors monthly spending
2. **At 80% threshold**: Email + SNS notification sent
3. **At 100% threshold**: Email + SNS notification sent
4. **SNS triggers remediation Lambda** (if configured)
5. **SSM Automation** stops EC2 instances tagged `AutoStop=true`
6. **Only tagged instances** are affected (safe by design)

## Cost Breakdown

**Expected Monthly Cost: ~$0.02/month**

### Detailed Breakdown

| Service | Usage | Free Tier | Cost |
|---------|-------|-----------|------|
| **Lambda** | 30 invocations/month, ~30s each, 256MB | 1M requests, 400K GB-sec | **$0.00** |
| **S3 Storage** | ~1GB | 5GB | **$0.02** |
| **S3 Requests** | 30 PUT/month | 20K requests | **$0.00** |
| **SES** | 30 emails/month | 1,000 emails | **$0.00** |
| **EventBridge Scheduler** | 30 invocations/month | 14M invocations | **$0.00** |
| **CloudWatch Logs** | ~200MB/month | 5GB ingestion, 5GB storage | **$0.00** |
| **CloudWatch Metrics** | ~180 metrics/month | 10K metrics | **$0.00** |
| **SSM Parameters** | 6 parameters | 10K parameters | **$0.00** |
| **SNS** | 0-2 notifications/month | 1M requests | **$0.00** |
| **Budgets** | 1 budget | Free service | **$0.00** |
| **Cost Explorer API** | 90-180 calls/month | Free | **$0.00** |
| **IAM** | Roles and policies | Free | **$0.00** |
| **TOTAL** | | | **~$0.02/month** |

### Annual Cost: ~$0.24/year

**Why so low?**
- Most services within AWS free tier limits
- Minimal usage (1 report per day)
- Efficient design (minimal storage/compute)
- S3 lifecycle policies (automatic cleanup)

## Monitoring & Alerts

### CloudWatch Alarms

The system monitors itself with these alarms:

| Alarm Name | What It Monitors | Action |
|------------|------------------|--------|
| `cost-alerting-reporter-errors` | Lambda errors | Creates OpsCenter OpsItem |
| `cost-alerting-reporter-duration` | Lambda timeout warnings | Logs warning |
| `cost-alerting-reporter-no-metrics` | No report generated | Creates OpsCenter OpsItem |
| `cost-alerting-scheduler-dlq-messages` | Scheduler failures | Creates OpsCenter OpsItem |
| `cost-alerting-remediation-errors` | Remediation Lambda errors | Creates OpsCenter OpsItem |

### Custom Metrics

If `enable_custom_metrics = true`, these metrics are published:

- `ReportGenerated`: Successful report generation
- `ReportFailed`: Failed report generation
- `EmailSent`: Email sent successfully
- `EmailFailed`: Email send failure
- `DailyTotalCost`: Yesterday's total cost
- `MTDTotalCost`: Month-to-date total cost

**View metrics:**
```bash
aws cloudwatch get-metric-statistics \
  --namespace cost-alerting \
  --metric-name ReportGenerated \
  --start-time 2025-01-01T00:00:00Z \
  --end-time 2025-01-02T00:00:00Z \
  --period 3600 \
  --statistics Sum
```

### Viewing Logs

```bash
# Reporter Lambda logs
aws logs tail /aws/lambda/cost-alerting-reporter --follow

# Remediation Lambda logs
aws logs tail /aws/lambda/cost-alerting-remediation --follow
```

## Security

### Security Features

✅ **S3 Bucket Security:**
- Encryption at rest (AES256)
- Versioning enabled
- HTTPS-only policy (no insecure connections)
- Public access blocked

✅ **IAM Least Privilege:**
- Roles scoped to specific resources
- No wildcard permissions
- Tag-based conditions for EC2 actions
- Namespace-scoped CloudWatch metrics

✅ **SSM Parameter Encryption:**
- Encrypted at rest by default
- Versioned for change tracking

✅ **SES Identity-Based Permissions:**
- Scoped to verified identities only
- No wildcard email permissions

✅ **Safe Remediation:**
- Only stops instances tagged `AutoStop=true`
- Requires explicit tagging (no accidental shutdowns)
- IAM conditions enforce tag requirement

### Best Practices

1. **Review IAM policies** before deploying
2. **Use SES sandbox mode** initially (requires recipient verification)
3. **Tag instances carefully** if using remediation
4. **Monitor CloudWatch alarms** regularly
5. **Review S3 bucket policies** for your use case

## Troubleshooting

### ❌ Lambda Invoke Permission Denied

**Error:** `AccessDeniedException: User is not authorized to perform: lambda:InvokeFunction`

**Solution:**
```bash
# Attach AWS managed policy
aws iam attach-user-policy \
  --user-name your-username \
  --policy-arn arn:aws:iam::aws:policy/AWSLambda_FullAccess

# Or use the provided policy file
aws iam put-user-policy \
  --user-name your-username \
  --policy-name cost-alerting-test \
  --policy-document file://terraform-policy.json
```

### ❌ Email Not Received

**Most common issue:** Email identities not verified in SES.

#### Step 1: Check SES Verification Status

```bash
# Check if your email is verified
aws ses get-identity-verification-attributes \
  --identities your-email@example.com \
  --region us-east-1
```

**Expected output:**
```json
{
    "VerificationAttributes": {
        "your-email@example.com": {
            "VerificationStatus": "Success",
            "VerificationToken": "..."
        }
    }
}
```

**If you see `"VerificationStatus": "Pending"`:**
1. Check your email inbox (including spam/junk)
2. Look for an email from `no-reply-aws@amazon.com` or `aws-verification@amazon.com`
3. Click the verification link in the email
4. Wait a few minutes and check again

**If you don't see a verification email:**
- Check spam/junk folder
- Request a new verification email:
  ```bash
  aws ses verify-email-identity \
    --email-address your-email@example.com \
    --region us-east-1
  ```

#### Step 2: Check Lambda Logs

```bash
# View recent Lambda logs
aws logs tail /aws/lambda/cost-alerting-reporter \
  --region us-east-1 \
  --since 30m \
  --format short
```

**Look for:**
- `Email sent successfully` - Email was sent successfully
- `EmailFailed` - Email sending failed
- `MessageRejected` - SES rejected the email
- `EmailAddressNotVerifiedException` - Email not verified

**Common errors:**
- `EmailAddressNotVerifiedException`: Email not verified (see Step 1)
- `MessageRejected`: Email address not verified or in sandbox mode
- `AccessDenied`: IAM permissions issue

#### Step 3: Verify SES Sandbox Mode

If `ses_sandbox_mode = true` in your `terraform.tfvars`, you can only send to verified email addresses.

**Check your configuration:**
```bash
cd infra
grep ses_sandbox_mode terraform.tfvars
```

**If in sandbox mode:**
- Both `report_from` AND `report_to` must be verified
- You can only send to verified email addresses
- To send to any email, request production access and set `ses_sandbox_mode = false`

#### Step 4: Check Email in Spam/Junk Folder

Sometimes emails go to spam. Check:
- Spam/Junk folder
- Promotions tab (Gmail)
- All Mail folder

#### Step 5: Test Email Sending Manually

Test if SES can send emails directly:

```bash
aws ses send-email \
  --from your-email@example.com \
  --to your-email@example.com \
  --subject "Test Email" \
  --text "This is a test email" \
  --region us-east-1
```

**If this fails:**
- Email is not verified
- Check error message for details

**If this succeeds:**
- SES is working
- Issue is likely in Lambda code or configuration

#### Step 6: Check SSM Parameter (Email Address)

The Lambda reads the recipient email from SSM Parameter Store. Verify it's correct:

```bash
aws ssm get-parameter \
  --name "/cost-alerting/report_to" \
  --region us-east-1
```

**If the email is wrong**, update it:
```bash
aws ssm put-parameter \
  --name "/cost-alerting/report_to" \
  --type "String" \
  --value "correct-email@example.com" \
  --overwrite \
  --region us-east-1
```

**Then verify the new email in SES** (see Step 1).

#### Step 7: Check Lambda Environment Variables

Verify the Lambda has the correct SES region:

```bash
aws lambda get-function-configuration \
  --function-name cost-alerting-reporter \
  --region us-east-1 \
  --query 'Environment.Variables.SES_REGION'
```

Should return: `"us-east-1"`

#### Step 8: Check IAM Permissions

Verify the Lambda role has SES permissions:

```bash
aws iam get-role-policy \
  --role-name cost-alerting-reporter-lambda \
  --policy-name cost-alerting-reporter-lambda-policy
```

**Look for:**
- `ses:SendEmail` permission
- Resource ARN should include your email identity

#### Quick Fix Checklist

- [ ] Email identity verified (check Step 1)
- [ ] Both `report_from` and `report_to` verified (if sandbox mode)
- [ ] Checked spam/junk folder
- [ ] Lambda logs show no errors
- [ ] SES can send test email (Step 5)
- [ ] SSM parameter has correct email address (Step 6)

#### Most Likely Solution

**90% of the time, it's unverified email identities.**

1. Check your inbox for verification emails
2. Click the verification links
3. Wait 2-3 minutes
4. Test Lambda again

### 📧 Changing Email Address

#### Quick Method: Update SSM Parameter (No Redeploy)

This updates the recipient email without redeploying Terraform.

**Step 1: Verify New Email in SES**
```bash
aws ses verify-email-identity \
  --email-address new-email@example.com \
  --region us-east-1
```

**Important:** Check your inbox for the verification email and click the link!

**Step 2: Update SSM Parameter**
```bash
aws ssm put-parameter \
  --name "/cost-alerting/report_to" \
  --type "String" \
  --value "new-email@example.com" \
  --overwrite \
  --region us-east-1
```

**Step 3: Test**
```bash
aws lambda invoke \
  --function-name cost-alerting-reporter \
  --region us-east-1 \
  --payload '{}' \
  /tmp/cost-report.json
```

#### Permanent Method: Update Terraform Config

**Step 1: Update terraform.tfvars**
```bash
cd infra
# Edit terraform.tfvars
# Change:
report_to = "new-email@example.com"
```

**Step 2: Verify Email in SES**
```bash
aws ses verify-email-identity \
  --email-address new-email@example.com \
  --region us-east-1
```

Check your inbox for verification email and click the link.

**Step 3: Apply Terraform**
```bash
terraform apply
```

This will:
- Update the SSM parameter
- Update SES identity (if needed)
- Keep everything in sync

**Note:** If in SES sandbox mode, you need to verify BOTH `report_from` and `report_to` email addresses.

### ❌ Lambda Not Receiving Invocations

**Check Scheduler:**
```bash
aws scheduler get-schedule \
  --name cost-alerting-daily-8pm \
  --group-name default \
  --region us-east-1 \
  --query 'State'
```

Should return: `"ENABLED"`

**Check DLQ for failures:**
```bash
aws sqs receive-message \
  --queue-url $(aws sqs get-queue-url \
    --queue-name cost-alerting-scheduler-dlq \
    --query QueueUrl --output text)
```

### ❌ Cost Explorer Queries Failing

- **Cost Explorer API is only available in `us-east-1`**
- Ensure Lambda has `ce:GetCostAndUsage` permission
- Check CloudWatch logs for detailed error messages
- Cost Explorer must be enabled in your AWS account (free)

### ❌ SSM Automation Document Creation Fails

If you see YAML parsing errors:
- Ensure `infra/ssm-automation-document.yaml` exists
- Check YAML syntax is valid
- Verify file encoding is UTF-8

### 🔍 Verifying Infrastructure in AWS Console

Use this checklist to verify all resources were created successfully:

#### Lambda Functions
**Location:** AWS Console → Lambda → Functions

**Expected:**
- ✅ `cost-alerting-reporter` - Main cost reporting function
- ✅ `cost-alerting-remediation` - Budget remediation function (if enabled)

**Check:** Both functions exist, status is "Active", environment variables are set correctly.

#### S3 Buckets
**Location:** AWS Console → S3 → Buckets

**Expected:**
- ✅ `cost-alerting-{account-id}-{region}`

**Check:** Bucket exists, versioning enabled, encryption configured, public access blocked.

#### EventBridge Scheduler
**Location:** AWS Console → EventBridge → Schedules

**Expected:**
- ✅ `cost-alerting-daily-8pm` - Schedule is enabled

**Check:** Schedule exists, target is correct Lambda function, retry policy configured.

#### SES Email Identities
**Location:** AWS Console → SES → Verified identities

**Expected:**
- ✅ `report_from` email - Status: "Verified"
- ✅ `report_to` email - Status: "Verified" (if sandbox mode)

**Check:** Both email addresses are verified. If not, check your inbox for verification links.

#### SSM Parameters
**Location:** AWS Console → Systems Manager → Parameter Store

**Expected:**
- ✅ `/cost-alerting/report_to`
- ✅ `/cost-alerting/report_from`
- ✅ `/cost-alerting/archive_bucket`
- ✅ `/cost-alerting/top_n_services`
- ✅ `/cost-alerting/include_mtd`
- ✅ `/cost-alerting/include_drivers`

**Check:** All 6 parameters exist with correct values.

#### CloudWatch Alarms
**Location:** AWS Console → CloudWatch → Alarms

**Expected:**
- ✅ `cost-alerting-reporter-errors`
- ✅ `cost-alerting-reporter-duration`
- ✅ `cost-alerting-reporter-no-metrics` (if custom metrics enabled)
- ✅ `cost-alerting-scheduler-dlq-messages`
- ✅ `cost-alerting-remediation-errors` (if remediation enabled)

**Check:** All alarms exist, state is "OK" (if system is healthy).

#### Quick Verification Commands

```bash
# Lambda functions
aws lambda list-functions --query 'Functions[?contains(FunctionName, `cost-alerting`)].FunctionName'

# S3 buckets
aws s3 ls | grep cost-alerting

# EventBridge Scheduler
aws scheduler list-schedules --schedule-group default --query 'Schedules[?contains(Name, `cost-alerting`)].Name'

# SES identities
aws ses list-identities --query 'Identities'

# SSM parameters
aws ssm describe-parameters --parameter-filters "Key=Name,Values=/cost-alerting/" --query 'Parameters[*].Name'

# CloudWatch alarms
aws cloudwatch describe-alarms --alarm-name-prefix cost-alerting --query 'MetricAlarms[*].AlarmName'
```

## Terraform Infrastructure Explained

This section provides detailed explanations for developers and employers.

### Core Files

- **`versions.tf`**: Terraform and provider version requirements
- **`providers.tf`**: AWS provider configuration with default tags
- **`variables.tf`**: All input variables with descriptions
- **`locals.tf`**: Computed values (SSM paths, ARNs, tags)
- **`outputs.tf`**: Resource outputs for reference

### Infrastructure Components

- **`s3.tf`**: Secure S3 bucket for report archives
- **`ssm.tf`**: Parameter Store for runtime configuration
- **`ses.tf`**: Email identity verification
- **`iam.tf`**: IAM roles and policies (least privilege)
- **`lambda.tf`**: Lambda functions (reporter & remediation)
- **`scheduler.tf`**: EventBridge Scheduler with DLQ
- **`monitoring.tf`**: CloudWatch alarms
- **`budgets.tf`**: AWS Budget with SNS integration
- **`automation.tf`**: SSM Automation document for remediation

### Design Decisions

1. **SSM Parameters vs Environment Variables**: Configuration stored in SSM allows runtime updates without redeploying Lambda
2. **S3 Lifecycle Policies**: Automatic cleanup of old reports reduces costs
3. **Tag-Based Remediation**: Only stops instances explicitly tagged, preventing accidental shutdowns
4. **DLQ for Scheduler**: Captures failed invocations for debugging
5. **Custom Metrics**: Optional metrics provide visibility into system health
6. **OpsCenter Integration**: Creates OpsItems for operational incidents

### Code Structure

```
AWS-ALERTING/
├── infra/                    # Terraform infrastructure
│   ├── *.tf                 # Terraform configuration files
│   ├── ssm-automation-document.yaml  # SSM Automation YAML
│   └── terraform.tfvars.example     # Configuration template
├── lambda/                   # Cost reporter Lambda
│   ├── app.py               # Main Lambda handler
│   └── requirements.txt     # Python dependencies
├── cost_remediation_lambda/ # Remediation Lambda
│   └── app.py              # Remediation handler
├── README.md                # This file
├── Makefile                 # Automation commands
├── .gitignore              # Git ignore rules
└── terraform-policy.json    # IAM policy for testing
```

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Support

- **Issues**: [GitHub Issues](https://github.com/alexlux58/AWS-ALERTING/issues)
- **Documentation**: This README
- **AWS Documentation**: [AWS Cost Explorer](https://docs.aws.amazon.com/cost-management/latest/userguide/what-is-cost-explorer.html)

## Acknowledgments

Built with:
- [Terraform](https://www.terraform.io/) - Infrastructure as Code
- [AWS Lambda](https://aws.amazon.com/lambda/) - Serverless compute
- [AWS Cost Explorer](https://aws.amazon.com/aws-cost-management/aws-cost-explorer/) - Cost analysis
- [EventBridge Scheduler](https://aws.amazon.com/eventbridge/scheduler/) - Scheduled execution

---

**Made with ❤️ for AWS cost management**
