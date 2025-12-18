resource "aws_ssm_parameter" "report_to" {
  name  = local.param_report_to
  type  = "String"
  value = var.report_to

  tags = local.common_tags
}

resource "aws_ssm_parameter" "report_from" {
  name  = local.param_report_from
  type  = "String"
  value = var.report_from

  tags = local.common_tags
}

resource "aws_ssm_parameter" "archive_bucket" {
  name  = local.param_archive_bucket
  type  = "String"
  value = aws_s3_bucket.archive.bucket

  tags = local.common_tags
}

resource "aws_ssm_parameter" "top_n_services" {
  name  = local.param_top_n_services
  type  = "String"
  value = tostring(var.top_n_services)

  tags = local.common_tags
}

resource "aws_ssm_parameter" "include_mtd" {
  name  = local.param_include_mtd
  type  = "String"
  value = tostring(var.include_mtd)

  tags = local.common_tags
}

resource "aws_ssm_parameter" "include_drivers" {
  name  = local.param_include_drivers
  type  = "String"
  value = tostring(var.include_drivers)

  tags = local.common_tags
}

