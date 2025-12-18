# IAM role for reporting Lambda
resource "aws_iam_role" "reporter_lambda" {
  name = "${var.project_name}-reporter-lambda"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy" "reporter_lambda" {
  name = "${var.project_name}-reporter-lambda-policy"
  role = aws_iam_role.reporter_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # CloudWatch Logs
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.reporter.arn}:*"
      },
      # Read SSM parameters
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters"
        ]
        Resource = [
          aws_ssm_parameter.report_to.arn,
          aws_ssm_parameter.report_from.arn,
          aws_ssm_parameter.archive_bucket.arn,
          aws_ssm_parameter.top_n_services.arn,
          aws_ssm_parameter.include_mtd.arn,
          aws_ssm_parameter.include_drivers.arn
        ]
      },
      # Write artifacts to S3
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:PutObjectAcl"
        ]
        Resource = "${aws_s3_bucket.archive.arn}/*"
      },
      # Send email via SES (scoped to verified identities)
      {
        Effect = "Allow"
        Action = [
          "ses:SendEmail",
          "ses:SendRawEmail"
        ]
        Resource = [
          aws_ses_email_identity.from.arn,
          var.ses_sandbox_mode ? aws_ses_email_identity.to[0].arn : "*"
        ]
      },
      # Cost Explorer API (must be in us-east-1)
      {
        Effect = "Allow"
        Action = [
          "ce:GetCostAndUsage",
          "ce:GetDimensionValues"
        ]
        Resource = "*"
      },
      # CloudWatch Metrics (for custom metrics)
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "cloudwatch:namespace" = var.project_name
          }
        }
      }
    ]
  })
}

# IAM role for EventBridge Scheduler
resource "aws_iam_role" "scheduler_invoke_lambda" {
  name = "${var.project_name}-scheduler-invoke"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "scheduler.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy" "scheduler_invoke_lambda" {
  name = "${var.project_name}-scheduler-invoke-policy"
  role = aws_iam_role.scheduler_invoke_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["lambda:InvokeFunction"]
        Resource = aws_lambda_function.reporter.arn
      }
    ]
  })
}

# IAM role for SSM Automation
resource "aws_iam_role" "automation_assume_role" {
  name = "${var.project_name}-automation-assume"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ssm.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy" "automation_assume_role" {
  name = "${var.project_name}-automation-assume-policy"
  role = aws_iam_role.automation_assume_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ec2:DescribeInstances"]
        Resource = "*"
      },
      # Stop only instances with AutoStop=true tag
      {
        Effect   = "Allow"
        Action   = ["ec2:StopInstances"]
        Resource = "*"
        Condition = {
          StringEquals = {
            "ec2:ResourceTag/AutoStop" = "true"
          }
        }
      }
    ]
  })
}

# IAM role for remediation Lambda
resource "aws_iam_role" "remediation_lambda" {
  name = "${var.project_name}-remediation-lambda"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy" "remediation_lambda" {
  name = "${var.project_name}-remediation-lambda-policy"
  role = aws_iam_role.remediation_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.remediation.arn}:*"
      },
      {
        Effect   = "Allow"
        Action   = ["ssm:StartAutomationExecution"]
        Resource = aws_ssm_document.stop_autostop_instances.arn
      }
    ]
  })
}

