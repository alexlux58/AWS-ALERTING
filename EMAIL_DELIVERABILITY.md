# Email Deliverability Guide

## Problem: Emails Going to Junk/Spam Folder

If your AWS Cost Alerting emails are being marked as junk or spam, this guide will help you fix the issue.

## Root Cause

Email providers (Gmail, Outlook, etc.) mark emails as junk when they cannot verify the sender. This happens because:

1. **Missing Email Authentication**: SPF, DKIM, and DMARC records help verify the sender
2. **Using Email Identity Instead of Domain Identity**: When using an email address you don't control (like `gmail.com`), you can't add DNS records
3. **SES Sandbox Mode**: In sandbox mode, SES has stricter limitations
4. **Low Sender Reputation**: New SES accounts start with no reputation

## Solutions (In Order of Effectiveness)

### ✅ Solution 1: Request SES Production Access (Recommended)

**This is the most important step!** Moving out of sandbox mode significantly improves deliverability.

1. **Go to AWS SES Console**: https://console.aws.amazon.com/ses/
2. **Click "Account dashboard"** in the left sidebar
3. **Click "Request production access"**
4. **Fill out the form**:
   - **Mail Type**: Transactional
   - **Website URL**: Your website or GitHub repo
   - **Use case description**: "Automated daily AWS cost reports sent to my personal email"
   - **Do you own or operate the domains**: No (if using email identity)
   - **How do you plan to build or maintain your list**: N/A (not applicable for transactional)
5. **Submit the request** (usually approved within 24 hours)

**After approval:**
1. Update `terraform.tfvars`:
   ```hcl
   ses_sandbox_mode = false
   ```
2. Run `terraform apply`

### ✅ Solution 2: Use a Custom Domain Identity (Best Long-term Solution)

If you own a domain (or can get one), using a domain identity gives you full control over email authentication.

**Benefits:**
- Full control over SPF, DKIM, and DMARC records
- Better sender reputation
- Professional appearance
- Can send from any email address on that domain

**Steps:**

1. **Add domain identity in Terraform** (update `infra/ses.tf`):
   ```hcl
   resource "aws_ses_domain_identity" "main" {
     domain = "yourdomain.com"
   }

   # Get DKIM tokens
   resource "aws_ses_domain_dkim" "main" {
     domain = aws_ses_domain_identity.main.domain
   }

   # Output DKIM tokens for DNS
   output "dkim_tokens" {
     value = aws_ses_domain_dkim.main.dkim_tokens
   }
   ```

2. **Run `terraform apply`** and note the DKIM tokens

3. **Add DNS records** to your domain:
   - **SPF Record** (TXT):
     ```
     v=spf1 include:amazonses.com ~all
     ```
   - **DKIM Records** (3 CNAME records):
     ```
     {token1}._domainkey.yourdomain.com -> {token1}.dkim.amazonses.com
     {token2}._domainkey.yourdomain.com -> {token2}.dkim.amazonses.com
     {token3}._domainkey.yourdomain.com -> {token3}.dkim.amazonses.com
     ```
   - **DMARC Record** (TXT):
     ```
     _dmarc.yourdomain.com -> v=DMARC1; p=quarantine; rua=mailto:your-email@yourdomain.com
     ```

4. **Update `terraform.tfvars`**:
   ```hcl
   report_from = "aws-costs@yourdomain.com"
   ```

5. **Verify domain** in SES console (takes a few minutes after DNS propagation)

### ✅ Solution 3: Verify DKIM is Enabled (For Email Identities)

AWS SES automatically enables DKIM signing for email identities, but let's verify:

```bash
# Check DKIM status
aws ses get-identity-dkim-attributes \
  --identities your-email@example.com \
  --region us-east-1
```

**Expected output:**
```json
{
  "DkimAttributes": {
    "your-email@example.com": {
      "DkimEnabled": true,
      "DkimVerificationStatus": "Success",
      "DkimTokens": []
    }
  }
}
```

If `DkimEnabled` is `false`, enable it:
```bash
aws ses put-identity-dkim-enabled \
  --identity your-email@example.com \
  --dkim-enabled \
  --region us-east-1
```

### ✅ Solution 4: Add Email to Safe Senders (Quick Fix)

While not a permanent solution, this helps immediately:

**For Gmail:**
1. Open the email in your inbox
2. Click the three dots (⋮) → "Add [sender] to contacts"
3. Or: Settings → Filters and Blocked Addresses → Create filter → Add sender → Never send to Spam

**For Outlook/Live:**
1. Open the email
2. Right-click sender → "Add to Safe Senders"
3. Or: Settings → Mail → Junk email → Safe senders → Add

### ✅ Solution 5: Improve Email Content

The Lambda already includes:
- ✅ Plain text version (for better deliverability)
- ✅ Proper HTML structure
- ✅ Clear subject line

**Additional improvements you can make:**
- Add a "Reply-To" header (if you want replies)
- Keep subject lines consistent
- Avoid spam trigger words

### ✅ Solution 6: Monitor SES Reputation

Check your SES sending statistics:

```bash
aws ses get-send-statistics --region us-east-1
```

**Key metrics to watch:**
- **Bounce Rate**: Should be < 5%
- **Complaint Rate**: Should be < 0.1%
- **Delivery Rate**: Should be > 95%

**If metrics are poor:**
- Remove invalid email addresses
- Ensure emails are expected (not unsolicited)
- Improve email content

## Verification Steps

After implementing solutions, verify everything is working:

### 1. Check Email Authentication

**For email identities:**
```bash
aws ses get-identity-verification-attributes \
  --identities your-email@example.com \
  --region us-east-1
```

Should show: `"VerificationStatus": "Success"`

**For domain identities:**
```bash
aws ses get-identity-verification-attributes \
  --identities yourdomain.com \
  --region us-east-1
```

Should show: `"VerificationStatus": "Success"`

### 2. Test Email Sending

```bash
aws ses send-email \
  --from your-email@example.com \
  --to recipient@example.com \
  --subject "Test Email - Deliverability Check" \
  --text "This is a test email to verify deliverability." \
  --region us-east-1
```

### 3. Check Email Headers

When you receive the email, check the headers:

**In Gmail:**
1. Open email → Click three dots → "Show original"
2. Look for:
   - `Authentication-Results`: Should show `dkim=pass`
   - `Received-SPF`: Should show `pass`

**In Outlook:**
1. Open email → File → Properties → Internet headers
2. Look for similar authentication results

## Quick Checklist

- [ ] Requested SES production access
- [ ] Verified email identity in SES
- [ ] Enabled DKIM signing (automatic for email identities)
- [ ] Added sender to safe senders list
- [ ] Checked SES sending statistics
- [ ] Tested email sending manually
- [ ] Verified email headers show authentication
- [ ] Considered using custom domain identity (best long-term)

## Most Common Fix

**90% of deliverability issues are solved by:**
1. Requesting SES production access
2. Verifying the email identity
3. Adding sender to safe senders list

## Still Having Issues?

If emails are still going to junk after trying these solutions:

1. **Check email headers** to see what's failing (SPF, DKIM, DMARC)
2. **Use a custom domain** instead of an email identity
3. **Contact AWS Support** if SES metrics look good but emails still fail
4. **Consider using AWS SES Configuration Sets** for better tracking

## Additional Resources

- [AWS SES Best Practices](https://docs.aws.amazon.com/ses/latest/dg/best-practices.html)
- [Improving Email Deliverability](https://docs.aws.amazon.com/ses/latest/dg/dg.html)
- [SES Production Access Request](https://console.aws.amazon.com/ses/home#/account)

