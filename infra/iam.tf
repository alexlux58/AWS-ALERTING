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
      # For domain identity: allow sending from the domain and the specific email address
      {
        Effect = "Allow"
        Action = [
          "ses:SendEmail",
          "ses:SendRawEmail"
        ]
        Resource = concat(
          local.is_domain_identity ? [
            aws_ses_domain_identity.from[0].arn,
            "arn:aws:ses:${var.aws_region}:${data.aws_caller_identity.current.account_id}:identity/${var.report_from}"
          ] : (length(aws_ses_email_identity.from) > 0 ? [aws_ses_email_identity.from[0].arn] : []),
          var.ses_sandbox_mode ? [aws_ses_email_identity.to[0].arn] : ["*"]
        )
      },
      # Cost Explorer API (must be in us-east-1)
      {
        Effect = "Allow"
        Action = [
          "ce:GetCostAndUsage",
          "ce:GetCostForecast",
          "ce:GetDimensionValues"
        ]
        Resource = "*"
      },
      # Budgets API (for budget status)
      {
        Effect = "Allow"
        Action = [
          "budgets:DescribeBudget",
          "budgets:ViewBudget"
        ]
        Resource = "arn:aws:budgets::${data.aws_caller_identity.current.account_id}:budget/${var.project_name}-monthly"
      },
      # STS (for getting account ID)
      {
        Effect = "Allow"
        Action = [
          "sts:GetCallerIdentity"
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

# IAM role for SSM Automation (only if remediation enabled)
resource "aws_iam_role" "automation_assume_role" {
  count = var.enable_remediation ? 1 : 0

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
  count = var.enable_remediation ? 1 : 0

  name = "${var.project_name}-automation-assume-policy"
  role = aws_iam_role.automation_assume_role[0].id

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

# IAM role for remediation Lambda (only if remediation enabled)
resource "aws_iam_role" "remediation_lambda" {
  count = var.enable_remediation ? 1 : 0

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
  count = var.enable_remediation ? 1 : 0

  name = "${var.project_name}-remediation-lambda-policy"
  role = aws_iam_role.remediation_lambda[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.remediation[0].arn}:*"
      },
      {
        Effect   = "Allow"
        Action   = ["ssm:StartAutomationExecution"]
        Resource = aws_ssm_document.stop_autostop_instances[0].arn
      }
    ]
  })
}

