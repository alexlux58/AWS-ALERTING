variable "project_name" {
  type        = string
  default     = "cost-alerting"
  description = "Project name used for resource naming"
}

variable "environment" {
  type        = string
  default     = "production"
  description = "Environment name (production, staging, etc.)"
}

variable "aws_region" {
  type        = string
  default     = "us-east-1"
  description = "AWS region for infrastructure"
}

variable "schedule_timezone" {
  type        = string
  default     = "America/Los_Angeles"
  description = "Timezone for the daily schedule (handles DST automatically)"
}

variable "schedule_cron" {
  type        = string
  default     = "cron(0 20 * * ? *)"
  description = "Cron expression for daily schedule (8:00 PM PT)"
}

variable "report_to" {
  type        = string
  description = "Email address to receive cost reports"
}

variable "report_from" {
  type        = string
  description = "Email address to send reports from (must be verified in SES)"
}

variable "ses_sandbox_mode" {
  type        = bool
  default     = true
  description = "If true, also verify recipient identity (required in SES sandbox mode)"
}

variable "top_n_services" {
  type        = number
  default     = 10
  description = "Number of top services to include in email report"
}

variable "include_mtd" {
  type        = bool
  default     = true
  description = "Include month-to-date cost breakdown in report"
}

variable "include_drivers" {
  type        = bool
  default     = true
  description = "Include usage type drivers in report"
}

variable "archive_retention_days" {
  type        = number
  default     = 365
  description = "Number of days to retain archived reports in S3"
}

variable "budget_limit_amount" {
  type        = string
  default     = "50"
  description = "Monthly budget limit in USD"
}

variable "budget_threshold_80" {
  type        = number
  default     = 80
  description = "Budget threshold percentage for first alert (80%)"
}

variable "budget_threshold_100" {
  type        = number
  default     = 100
  description = "Budget threshold percentage for second alert (100%)"
}

variable "lambda_timeout" {
  type        = number
  default     = 300
  description = "Lambda function timeout in seconds"
}

variable "lambda_memory_size" {
  type        = number
  default     = 256
  description = "Lambda function memory size in MB"
}

variable "log_retention_days" {
  type        = number
  default     = 30
  description = "CloudWatch Logs retention in days"
}

variable "scheduler_retry_attempts" {
  type        = number
  default     = 2
  description = "Number of retry attempts for EventBridge Scheduler"
}

variable "enable_custom_metrics" {
  type        = bool
  default     = true
  description = "Enable custom CloudWatch metrics for monitoring"
}

variable "enable_opsitem_alarms" {
  type        = bool
  default     = false
  description = "Enable OpsCenter OpsItem creation on alarms (requires OpsCenter to be enabled)"
}

