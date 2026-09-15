variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "security_group_id" {
  type = string
}

variable "instance_class" {
  description = "db.t4g.micro to start (docs/aws-production-architecture.md §11/§12) - this app's DB load is small (user rows + run-state rows), not project/media content. Right-size from real CloudWatch metrics, not preemptively."
  type        = string
  default     = "db.t4g.micro"
}

variable "allocated_storage_gb" {
  type    = number
  default = 20
}

variable "max_allocated_storage_gb" {
  description = "Storage autoscaling ceiling - lets RDS grow storage automatically under real usage without a manual resize, capped so it can't runaway on cost."
  type        = number
  default     = 100
}

variable "engine_version" {
  type    = string
  default = "16"
}

variable "multi_az" {
  description = <<-EOT
    False by default (docs/aws-production-architecture.md §12): Multi-AZ
    roughly doubles RDS cost for automatic failover this app's user base
    likely doesn't need on day one. Automated backups + PITR (both always
    on regardless of this flag) already protect against data loss, just
    not against an availability gap during an AZ failure - a deliberately
    accepted, documented risk (see §14), not an oversight. Flip to true
    once real usage justifies it.
  EOT
  type        = bool
  default     = false
}

variable "backup_retention_days" {
  type    = number
  default = 7
}

variable "deletion_protection" {
  description = "True by default. This database holds user accounts and (once migrated, see docs/aws-production-architecture.md §5) run state - an accidental `terraform destroy` or console delete should require deliberately turning this off first, not succeed silently."
  type        = bool
  default     = true
}

variable "database_name" {
  type    = string
  default = "ai_video_studio"
}

variable "master_username" {
  type    = string
  default = "app_admin"
}

variable "tags" {
  type    = map(string)
  default = {}
}
