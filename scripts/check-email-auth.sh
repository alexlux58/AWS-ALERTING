#!/bin/bash
# Script to check and enable email authentication for AWS SES

set -e

REGION="${AWS_REGION:-us-east-1}"
FROM_EMAIL="${1:-your-email@example.com}"

echo "🔍 Checking email authentication for: $FROM_EMAIL"
echo "📍 Region: $REGION"
echo ""

# Check verification status
echo "1️⃣ Checking verification status..."
VERIFICATION=$(aws ses get-identity-verification-attributes \
  --identities "$FROM_EMAIL" \
  --region "$REGION" \
  --query "VerificationAttributes.\"$FROM_EMAIL\".VerificationStatus" \
  --output text 2>/dev/null || echo "NotVerified")

if [ "$VERIFICATION" = "Success" ]; then
  echo "   ✅ Email is verified"
else
  echo "   ❌ Email is NOT verified (Status: $VERIFICATION)"
  echo "   📧 Request verification email:"
  echo "      aws ses verify-email-identity --email-address $FROM_EMAIL --region $REGION"
  exit 1
fi

# Check DKIM status
echo ""
echo "2️⃣ Checking DKIM status..."
DKIM_ENABLED=$(aws ses get-identity-dkim-attributes \
  --identities "$FROM_EMAIL" \
  --region "$REGION" \
  --query "DkimAttributes.\"$FROM_EMAIL\".DkimEnabled" \
  --output text 2>/dev/null || echo "false")

DKIM_STATUS=$(aws ses get-identity-dkim-attributes \
  --identities "$FROM_EMAIL" \
  --region "$REGION" \
  --query "DkimAttributes.\"$FROM_EMAIL\".DkimVerificationStatus" \
  --output text 2>/dev/null || echo "NotEnabled")

if [ "$DKIM_ENABLED" = "true" ]; then
  echo "   ✅ DKIM is enabled"
  if [ "$DKIM_STATUS" = "Success" ]; then
    echo "   ✅ DKIM verification: Success"
  else
    echo "   ⚠️  DKIM verification: $DKIM_STATUS"
  fi
else
  echo "   ❌ DKIM is NOT enabled"
  echo "   🔧 Enabling DKIM..."
  aws ses put-identity-dkim-enabled \
    --identity "$FROM_EMAIL" \
    --dkim-enabled \
    --region "$REGION"
  echo "   ✅ DKIM enabled! It may take a few minutes to propagate."
fi

# Check SES account status
echo ""
echo "3️⃣ Checking SES account status..."
SES_STATUS=$(aws ses get-account-sending-enabled \
  --region "$REGION" \
  --query "Enabled" \
  --output text 2>/dev/null || echo "false")

if [ "$SES_STATUS" = "true" ]; then
  echo "   ✅ SES sending is enabled"
else
  echo "   ❌ SES sending is disabled"
fi

# Check if in sandbox mode
echo ""
echo "4️⃣ Checking sandbox status..."
# Try to send to an unverified email to check sandbox mode
# This is a heuristic - if we get a specific error, we're in sandbox
echo "   ℹ️  To check sandbox mode, look in AWS Console:"
echo "      https://console.aws.amazon.com/ses/home?region=$REGION#/account"
echo "      If you see 'Request production access', you're in sandbox mode"

# Get sending statistics
echo ""
echo "5️⃣ Recent sending statistics (last 24 hours)..."
aws ses get-send-statistics \
  --region "$REGION" \
  --query "SendDataPoints[-24:].{Timestamp:Timestamp,Bounces:Bounces,Complaints:Complaints,DeliveryAttempts:DeliveryAttempts}" \
  --output table 2>/dev/null || echo "   ⚠️  No statistics available yet"

echo ""
echo "✅ Email authentication check complete!"
echo ""
echo "📚 For more help, see: EMAIL_DELIVERABILITY.md"
echo ""
echo "💡 Quick fixes:"
echo "   1. Request SES production access (most important!)"
echo "   2. Add sender to safe senders list in your email client"
echo "   3. Verify DKIM is enabled (done above)"

