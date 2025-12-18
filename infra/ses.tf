resource "aws_ses_email_identity" "from" {
  email = var.report_from
}

resource "aws_ses_email_identity" "to" {
  count = var.ses_sandbox_mode ? 1 : 0
  email = var.report_to
}

# Note: After terraform apply, check inbox for verification emails
# and click the verification links before the Lambda can send emails.

