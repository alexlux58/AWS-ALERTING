# SNS topic for budget alerts
resource "aws_sns_topic" "budget_alerts" {
  name = "${var.project_name}-budget-alerts"

  tags = local.common_tags
}

# Optional: receive SNS budget alerts directly as email
resource "aws_sns_topic_subscription" "budget_email" {
  topic_arn = aws_sns_topic.budget_alerts.arn
  protocol  = "email"
  endpoint  = var.report_to
}

# Monthly cost budget
resource "aws_budgets_budget" "monthly_cost" {
  name              = "${var.project_name}-monthly"
  budget_type       = "COST"
  limit_amount      = var.budget_limit_amount
  limit_unit        = "USD"
  time_unit         = "MONTHLY"
  time_period_start = "${formatdate("YYYY-MM", timestamp())}-01_00:00"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = var.budget_threshold_80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.report_to]
    subscriber_sns_topic_arns  = [aws_sns_topic.budget_alerts.arn]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = var.budget_threshold_100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.report_to]
    subscriber_sns_topic_arns  = [aws_sns_topic.budget_alerts.arn]
  }

  tags = local.common_tags
}

# SNS subscription for Lambda (remediation)
resource "aws_sns_topic_subscription" "budget_to_lambda" {
  topic_arn = aws_sns_topic.budget_alerts.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.remediation.arn
}

# Lambda permission for SNS
resource "aws_lambda_permission" "allow_sns_invoke_remediation" {
  statement_id  = "AllowSNSInvokeRemediation"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.remediation.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.budget_alerts.arn
}

