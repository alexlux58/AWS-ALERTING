# CloudWatch Log Group for reporter Lambda
resource "aws_cloudwatch_log_group" "reporter" {
  name              = "/aws/lambda/${var.project_name}-reporter"
  retention_in_days = var.log_retention_days

  tags = local.common_tags
}

# Archive Lambda code
# Note: For production, you may want to install dependencies first:
# cd ../lambda && pip install -r requirements.txt -t .
data "archive_file" "reporter_zip" {
  type        = "zip"
  source_file = "${path.module}/../lambda/app.py"
  output_path = "${path.module}/.build/reporter.zip"
}

# Reporter Lambda function
resource "aws_lambda_function" "reporter" {
  function_name = "${var.project_name}-reporter"
  role          = aws_iam_role.reporter_lambda.arn
  handler       = "app.lambda_handler"
  runtime       = "python3.11"
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory_size

  filename         = data.archive_file.reporter_zip.output_path
  source_code_hash = data.archive_file.reporter_zip.output_base64sha256

  environment {
    variables = {
      SES_REGION            = var.aws_region # SES region (AWS_REGION is reserved, set automatically by Lambda)
      SCHEDULE_TZ           = var.schedule_timezone
      PARAM_REPORT_TO       = local.param_report_to
      PARAM_REPORT_FROM     = local.param_report_from
      PARAM_ARCHIVE_BUCKET  = local.param_archive_bucket
      PARAM_TOP_N_SERVICES  = local.param_top_n_services
      PARAM_INCLUDE_MTD     = local.param_include_mtd
      PARAM_INCLUDE_DRIVERS = local.param_include_drivers
      ENABLE_METRICS        = tostring(var.enable_custom_metrics)
      METRICS_NAMESPACE     = var.project_name
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.reporter,
    aws_iam_role_policy.reporter_lambda
  ]

  tags = local.common_tags
}

# CloudWatch Log Group for remediation Lambda
resource "aws_cloudwatch_log_group" "remediation" {
  name              = "/aws/lambda/${var.project_name}-remediation"
  retention_in_days = var.log_retention_days

  tags = local.common_tags
}

# Archive remediation Lambda code
data "archive_file" "remediation_zip" {
  type        = "zip"
  source_file = "${path.module}/../cost_remediation_lambda/app.py"
  output_path = "${path.module}/.build/remediation.zip"
}

# Remediation Lambda function
resource "aws_lambda_function" "remediation" {
  function_name = "${var.project_name}-remediation"
  role          = aws_iam_role.remediation_lambda.arn
  handler       = "app.lambda_handler"
  runtime       = "python3.11"
  timeout       = 60
  memory_size   = 128

  filename         = data.archive_file.remediation_zip.output_path
  source_code_hash = data.archive_file.remediation_zip.output_base64sha256

  environment {
    variables = {
      AUTOMATION_DOC_NAME        = aws_ssm_document.stop_autostop_instances.name
      AUTOMATION_ASSUME_ROLE_ARN = aws_iam_role.automation_assume_role.arn
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.remediation,
    aws_iam_role_policy.remediation_lambda
  ]

  tags = local.common_tags
}

