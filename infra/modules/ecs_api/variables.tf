variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "cluster_arn" {
  type = string
}

variable "cluster_name" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "security_group_id" {
  type = string
}

variable "target_group_arn" {
  type = string
}

variable "execution_role_arn" {
  type = string
}

variable "task_role_arn" {
  type = string
}

variable "log_group_name" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "ecr_repository_url" {
  type = string
}

variable "image_tag" {
  type    = string
  default = "latest"
}

variable "container_port" {
  type    = number
  default = 8000
}

variable "cpu" {
  description = "0.5 vCPU to start (docs/aws-production-architecture.md §11) - Python/FastAPI here is I/O-bound (LLM HTTP calls, no local ML/media libraries), not CPU-bound. Right-size from real CloudWatch metrics."
  type        = number
  default     = 512
}

variable "memory" {
  type    = number
  default = 1024
}

variable "min_capacity" {
  description = <<-EOT
    Default 1. docs/aws-production-architecture.md §0/§13: RunRegistry is
    in-memory and single-process in the CURRENT application code - do not
    raise this above 1 until it's been migrated to RDS (see §5), or you
    silently break SSE progress and run-status lookups for requests that
    land on a different task than the one that started a run, exactly as
    already documented for the existing Railway deployment.
  EOT
  type        = number
  default     = 1
}

variable "max_capacity" {
  type    = number
  default = 4
}

variable "cors_origins" {
  description = "DASHBOARD_CORS_ORIGINS - comma-separated frontend origin(s). The frontend stays on Vercel (docs/aws-production-architecture.md §0) unless this changes."
  type        = string
}

variable "pipeline_max_concurrency" {
  type    = number
  default = 4
}

variable "pipeline_timeout_seconds" {
  type    = number
  default = 1800
}

variable "s3_bucket_name" {
  type = string
}

variable "sqs_queue_url" {
  type = string
}

variable "db_host" {
  type = string
}

variable "db_port" {
  type = number
}

variable "db_name" {
  type = string
}

variable "db_master_secret_arn" {
  type = string
}

variable "llm_key_parameter_arns" {
  type = map(string)
}

variable "jwt_signing_key_parameter_arn" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
