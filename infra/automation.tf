# SSM Automation document to stop instances tagged AutoStop=true
# Only created if enable_remediation = true
resource "aws_ssm_document" "stop_autostop_instances" {
  count = var.enable_remediation ? 1 : 0

  name            = "${var.project_name}-StopAutoStopInstances"
  document_type   = "Automation"
  document_format = "YAML"

  content = file("${path.module}/ssm-automation-document.yaml")

  tags = local.common_tags
}

