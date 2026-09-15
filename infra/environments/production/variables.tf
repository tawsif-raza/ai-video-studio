variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "project_name" {
  type    = string
  default = "ai-video-studio"
}

variable "environment" {
  type    = string
  default = "production"
}

variable "azs" {
  type    = list(string)
  default = ["ap-south-1a", "ap-south-1b"]
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "enable_second_nat_gateway" {
  type    = bool
  default = false
}

# --- Frontend / CORS ---

variable "cors_origins" {
  description = "DASHBOARD_CORS_ORIGINS for the API service - the deployed frontend origin(s). The frontend stays on Vercel (docs/aws-production-architecture.md §0)."
  type        = string
  default     = "https://ai-video-studio-dashboard.vercel.app"
}

# --- DNS / TLS (optional - leave domain_name empty to skip) ---

variable "domain_name" {
  description = "e.g. api.yourdomain.com. Empty skips Route 53/ACM entirely and the ALB gets an HTTP-only listener."
  type        = string
  default     = ""
}

variable "create_dns_zone" {
  type    = bool
  default = false
}

variable "existing_dns_zone_id" {
  type    = string
  default = ""
}

# --- ECR / container image ---

variable "image_tag" {
  description = "Set by the deploy pipeline (docs/aws-production-architecture.md §9) - defaults to a tag that will not resolve until a real image is pushed, deliberately, so a stray apply can't accidentally deploy nothing."
  type        = string
  default     = "placeholder-build-and-push-first"
}

# --- RDS ---

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "db_multi_az" {
  type    = bool
  default = false
}

variable "db_deletion_protection" {
  type    = bool
  default = true
}

# --- ECS sizing ---

variable "api_cpu" {
  type    = number
  default = 512
}

variable "api_memory" {
  type    = number
  default = 1024
}

variable "api_min_capacity" {
  description = "Do not raise above 1 until RunRegistry is migrated to RDS - see modules/ecs_api/variables.tf and docs/aws-production-architecture.md §0/§5/§13."
  type        = number
  default     = 1
}

variable "api_max_capacity" {
  type    = number
  default = 4
}

variable "worker_cpu" {
  type    = number
  default = 1024
}

variable "worker_memory" {
  type    = number
  default = 2048
}

variable "worker_max_capacity" {
  type    = number
  default = 10
}

variable "use_fargate_spot_for_worker" {
  type    = bool
  default = true
}

variable "pipeline_max_concurrency" {
  type    = number
  default = 4
}

variable "pipeline_timeout_seconds" {
  type    = number
  default = 1800
}

# --- S3 ---

variable "s3_force_destroy" {
  description = "Keep false - see modules/s3/variables.tf."
  type        = bool
  default     = false
}

# --- Monitoring ---

variable "log_retention_days" {
  type    = number
  default = 60
}

variable "alarm_email" {
  type    = string
  default = ""
}
