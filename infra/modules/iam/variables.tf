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

variable "ses_region" {
  description = "Region the SES sending identity lives in - used to build the identity ARN the api_task role's SES permission is scoped to. Blank disables the SES statement entirely (matches ses_from_email being blank - see that variable)."
  type        = string
  default     = ""
}

variable "ses_from_email" {
  description = "Verified SES sender identity (email address) the API task role is allowed to send as. Blank grants no SES permission at all - the API task role gets no SES access unless a real verified identity is configured, keeping this additive/optional like the S3/SQS/RDS prerequisites above."
  type        = string
  default     = ""
}

variable "tags" {
  type    = map(string)
  default = {}
}
