# Dead Letter Queue for Scheduler failures
resource "aws_sqs_queue" "scheduler_dlq" {
  name                      = "${var.project_name}-scheduler-dlq"
  message_retention_seconds = 1209600 # 14 days

  tags = local.common_tags
}

# SQS queue policy for DLQ (allow Scheduler to send messages)
resource "aws_sqs_queue_policy" "scheduler_dlq" {
  queue_url = aws_sqs_queue.scheduler_dlq.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "scheduler.amazonaws.com"
        }
        Action   = "sqs:SendMessage"
        Resource = aws_sqs_queue.scheduler_dlq.arn
      }
    ]
  })
}

# Scheduler IAM role (already defined in iam.tf)
# Scheduler schedule with retries and DLQ
resource "aws_scheduler_schedule" "daily_7am" {
  name       = "${var.project_name}-daily-7am"
  group_name = "default"

  schedule_expression          = var.schedule_cron
  schedule_expression_timezone = var.schedule_timezone

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.reporter.arn
    role_arn = aws_iam_role.scheduler_invoke_lambda.arn

    retry_policy {
      maximum_retry_attempts = var.scheduler_retry_attempts
    }

    dead_letter_config {
      arn = aws_sqs_queue.scheduler_dlq.arn
    }
  }

  state = "ENABLED"
}

# Lambda permission for Scheduler
resource "aws_lambda_permission" "allow_scheduler" {
  statement_id  = "AllowEventBridgeSchedulerInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.reporter.function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = aws_scheduler_schedule.daily_7am.arn
}

# CloudWatch alarm for DLQ messages (indicates scheduler failures)
resource "aws_cloudwatch_metric_alarm" "scheduler_dlq" {
  alarm_name          = "${var.project_name}-scheduler-dlq-messages"
  alarm_description   = "Alerts when messages are sent to scheduler DLQ"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "NumberOfMessagesReceived"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.scheduler_dlq.name
  }

  alarm_actions = local.opsitem_action_arn != null ? [local.opsitem_action_arn] : []

  tags = local.common_tags
}

