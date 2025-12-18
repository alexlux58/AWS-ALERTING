# SSM Automation document to stop instances tagged AutoStop=true
resource "aws_ssm_document" "stop_autostop_instances" {
  name            = "${var.project_name}-StopAutoStopInstances"
  document_type   = "Automation"
  document_format = "YAML"

  content = file("${path.module}/ssm-automation-document.yaml")

  tags = local.common_tags
}

