# Extract domain from email address (e.g., "admin@alexflux.com" -> "alexflux.com")
locals {
  from_domain = replace(var.report_from, "/^[^@]+@(.+)$/", "$1")
  is_domain_identity = var.report_from != "" && can(regex("^[^@]+@", var.report_from))
}

# Domain identity for the sending domain (better deliverability)
resource "aws_ses_domain_identity" "from" {
  count  = local.is_domain_identity ? 1 : 0
  domain = local.from_domain
}

# Enable DKIM signing for the domain
resource "aws_ses_domain_dkim" "from" {
  count  = local.is_domain_identity ? 1 : 0
  domain = aws_ses_domain_identity.from[0].domain
}

# Fallback: Email identity if not using a domain
resource "aws_ses_email_identity" "from" {
  count = local.is_domain_identity ? 0 : 1
  email = var.report_from
}

# Recipient email identity (only needed in sandbox mode)
resource "aws_ses_email_identity" "to" {
  count = var.ses_sandbox_mode ? 1 : 0
  email = var.report_to
}

# Note: After terraform apply, you need to add DNS records to verify the domain.
# Run: terraform output -json dns_records
# Then add the TXT and CNAME records to your domain's DNS.
#
# IMPORTANT: Domain identity provides better email deliverability:
# - Full control over SPF, DKIM, and DMARC records
# - Better sender reputation
# - Professional appearance
# See EMAIL_DELIVERABILITY.md for detailed DNS setup instructions.

