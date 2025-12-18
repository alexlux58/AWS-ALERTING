locals {
  ssm_prefix = "/${var.project_name}"

  param_report_to       = "${local.ssm_prefix}/report_to"
  param_report_from     = "${local.ssm_prefix}/report_from"
  param_archive_bucket  = "${local.ssm_prefix}/archive_bucket"
  param_top_n_services  = "${local.ssm_prefix}/top_n_services"
  param_include_mtd     = "${local.ssm_prefix}/include_mtd"
  param_include_drivers = "${local.ssm_prefix}/include_drivers"

  # OpsCenter severity/category for CloudWatch alarm action
  # Format: arn:aws:ssm:<region>:<account_id>:opsitem:<severity>#CATEGORY=<category>
  # Note: If OpsCenter is not enabled, set enable_opsitem_alarms = false
  # Valid categories: Availability, Performance, Security, Cost, Recovery, OperationalExcellence
  opsitem_action_arn = var.enable_opsitem_alarms ? "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:opsitem:3#CATEGORY=Cost" : null

  # Common resource tags
  common_tags = {
    Project     = var.project_name
    ManagedBy   = "Terraform"
    Environment = var.environment
  }
}

