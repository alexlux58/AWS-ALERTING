# CloudWatch alarm for Lambda errors
resource "aws_cloudwatch_metric_alarm" "reporter_errors" {
  alarm_name          = "${var.project_name}-reporter-errors"
  alarm_description   = "Creates an OpsCenter OpsItem when the daily cost reporter Lambda errors"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.reporter.function_name
  }

  alarm_actions = local.opsitem_action_arn != null ? [local.opsitem_action_arn] : []

  tags = local.common_tags
}

# CloudWatch alarm for Lambda duration (indicates potential issues)
resource "aws_cloudwatch_metric_alarm" "reporter_duration" {
  alarm_name          = "${var.project_name}-reporter-duration"
  alarm_description   = "Alerts when Lambda execution time exceeds 80% of timeout"
  namespace           = "AWS/Lambda"
  metric_name         = "Duration"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  threshold           = var.lambda_timeout * 1000 * 0.8 # 80% of timeout in milliseconds
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.reporter.function_name
  }

  tags = local.common_tags
}

# CloudWatch alarm for no custom metrics (indicates Lambda didn't complete successfully)
resource "aws_cloudwatch_metric_alarm" "reporter_no_metrics" {
  count = var.enable_custom_metrics ? 1 : 0

  alarm_name          = "${var.project_name}-reporter-no-metrics"
  alarm_description   = "Alerts when no custom metrics are emitted (Lambda may have failed silently)"
  namespace           = var.project_name
  metric_name         = "ReportGenerated"
  statistic           = "Sum"
  period              = 3600 # 1 hour
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching" # Missing data means no report was generated

  alarm_actions = local.opsitem_action_arn != null ? [local.opsitem_action_arn] : []

  tags = local.common_tags
}

# CloudWatch alarm for remediation Lambda errors (only if remediation enabled)
resource "aws_cloudwatch_metric_alarm" "remediation_errors" {
  count = var.enable_remediation ? 1 : 0

  alarm_name          = "${var.project_name}-remediation-errors"
  alarm_description   = "Alerts when remediation Lambda errors"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.remediation[0].function_name
  }

  alarm_actions = local.opsitem_action_arn != null ? [local.opsitem_action_arn] : []

  tags = local.common_tags
}

