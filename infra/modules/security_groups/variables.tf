variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "vpc_endpoints_sg_id" {
  description = "Security group on the interface VPC endpoints (module.networking), so the API service can reach SQS/Secrets Manager/CloudWatch Logs without NAT."
  type        = string
}

variable "container_port" {
  type    = number
  default = 8000
}

variable "api_allow_internet_egress" {
  description = <<-EOT
    Transitional flag, default false. The TARGET architecture
    (docs/aws-production-architecture.md) has the API service never call
    external LLM providers directly - only the worker service does, via
    SQS - so the API service needs no path to the public internet at all
    (VPC endpoints cover S3/SQS/Secrets/Logs; RDS is in-VPC).
    Only flip this to true if you are deploying the CURRENT, unmodified
    application image (which still makes LLM calls from inside the API
    process - see docs/aws-production-architecture.md's "critical
    question") as a stopgap BEFORE the worker-split code change lands.
    Prefer landing that code change first.
  EOT
  type        = bool
  default     = false
}

variable "alb_ingress_cidrs" {
  description = "CIDRs allowed to reach the ALB on 80/443. Defaults to the whole internet (real production, once security checks have passed) - staging deliberately overrides this to a narrow CIDR (e.g. one IP/32) so the environment is never publicly exposed before its own security review."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "tags" {
  type    = map(string)
  default = {}
}
