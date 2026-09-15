variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "ecr_repository_arn" {
  type = string
}

variable "s3_bucket_arn" {
  type = string
}

variable "s3_kms_key_arn" {
  type = string
}

variable "sqs_queue_arn" {
  type = string
}

variable "rds_master_secret_arn" {
  type = string
}

variable "llm_key_parameter_arns" {
  type = map(string)
}

variable "jwt_signing_key_parameter_arn" {
  type = string
}

variable "log_group_arns" {
  description = "ARNs of the CloudWatch log groups both task execution roles need to write to."
  type        = list(string)
}

variable "tags" {
  type    = map(string)
  default = {}
}
