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

variable "cpu" {
  description = "1 vCPU to start (docs/aws-production-architecture.md §11) - real ffmpeg CPU/RAM needs under load were NOT independently measured in the stability audit (no ffmpeg available in that environment); tune from real CloudWatch metrics after launch."
  type        = number
  default     = 1024
}

variable "memory" {
  type    = number
  default = 2048
}

variable "min_capacity" {
  description = "0 by default (docs/aws-production-architecture.md §3/§12) - a valid, cost-saving steady state when no jobs are queued. Scales out on SQS backlog (see aws_appautoscaling_policy in this module)."
  type        = number
  default     = 0
}

variable "max_capacity" {
  type    = number
  default = 10
}

variable "use_fargate_spot" {
  description = "docs/aws-production-architecture.md §12: video generation jobs are already designed to be retryable (idempotent render output, SQS redelivery on failure) - a Spot interruption just means the message becomes visible again and another task picks it up. ~70% cheaper than on-demand Fargate."
  type        = bool
  default     = true
}

variable "sqs_queue_name" {
  type = string
}

variable "sqs_queue_url" {
  type = string
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

variable "tags" {
  type    = map(string)
  default = {}
}
