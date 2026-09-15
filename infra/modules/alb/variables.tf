variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "security_group_id" {
  type = string
}

variable "container_port" {
  type    = number
  default = 8000
}

variable "certificate_arn" {
  description = "ACM certificate ARN for the HTTPS listener. If empty, only an HTTP listener is created (no domain configured yet - see modules/dns) - NOT recommended for real production traffic, but unblocks a first deploy before DNS/ACM is set up."
  type        = string
  default     = ""
}

variable "deletion_protection" {
  type    = bool
  default = true
}

variable "tags" {
  type    = map(string)
  default = {}
}
