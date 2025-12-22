output "archive_bucket" {
  description = "S3 bucket name for archived cost reports"
  value       = aws_s3_bucket.archive.bucket
}

output "archive_bucket_arn" {
  description = "S3 bucket ARN for archived cost reports"
  value       = aws_s3_bucket.archive.arn
}

output "reporter_lambda_name" {
  description = "Name of the cost reporting Lambda function"
  value       = aws_lambda_function.reporter.function_name
}

output "reporter_lambda_arn" {
  description = "ARN of the cost reporting Lambda function"
  value       = aws_lambda_function.reporter.arn
}

output "remediation_lambda_name" {
  description = "Name of the remediation Lambda function"
  value       = var.enable_remediation ? aws_lambda_function.remediation[0].function_name : null
}

output "budget_sns_topic" {
  description = "SNS topic ARN for budget alerts"
  value       = aws_sns_topic.budget_alerts.arn
}

output "scheduler_schedule_arn" {
  description = "ARN of the EventBridge Scheduler schedule"
  value       = aws_scheduler_schedule.daily_7am.arn
}

output "scheduler_dlq_arn" {
  description = "ARN of the Scheduler dead letter queue"
  value       = aws_sqs_queue.scheduler_dlq.arn
}

output "automation_document_name" {
  description = "Name of the SSM Automation document"
  value       = var.enable_remediation ? aws_ssm_document.stop_autostop_instances[0].name : null
}

output "ses_from_identity" {
  description = "SES identity for sending reports (domain or email)"
  value       = local.is_domain_identity ? aws_ses_domain_identity.from[0].domain : (length(aws_ses_email_identity.from) > 0 ? aws_ses_email_identity.from[0].email : null)
}

output "ses_to_identity" {
  description = "SES email identity for receiving reports (if sandbox mode)"
  value       = var.ses_sandbox_mode ? aws_ses_email_identity.to[0].email : null
}

output "dns_records" {
  description = "DNS records required to verify and authenticate the domain"
  value = local.is_domain_identity ? {
    verification_record = {
      name  = "_amazonses.${aws_ses_domain_identity.from[0].domain}"
      type  = "TXT"
      value = aws_ses_domain_identity.from[0].verification_token
    }
    dkim_records = [
      for token in aws_ses_domain_dkim.from[0].dkim_tokens : {
        name  = "${token}._domainkey.${aws_ses_domain_identity.from[0].domain}"
        type  = "CNAME"
        value = "${token}.dkim.amazonses.com"
      }
    ]
    spf_record = {
      name  = aws_ses_domain_identity.from[0].domain
      type  = "TXT"
      value = "v=spf1 include:amazonses.com ~all"
      note  = "Optional but recommended for better deliverability"
    }
    dmarc_record = {
      name  = "_dmarc.${aws_ses_domain_identity.from[0].domain}"
      type  = "TXT"
      value = "v=DMARC1; p=quarantine; rua=mailto:${var.report_from}"
      note  = "Optional but recommended for better deliverability"
    }
  } : null
}

# Note: Use 'terraform output -json dns_records' to get the DNS records needed
# for domain verification. See EMAIL_DELIVERABILITY.md for setup instructions.

