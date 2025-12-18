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
  value       = aws_scheduler_schedule.daily_8pm.arn
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
  description = "SES email identity for sending reports"
  value       = aws_ses_email_identity.from.email
}

output "ses_to_identity" {
  description = "SES email identity for receiving reports (if sandbox mode)"
  value       = var.ses_sandbox_mode ? aws_ses_email_identity.to[0].email : null
}

