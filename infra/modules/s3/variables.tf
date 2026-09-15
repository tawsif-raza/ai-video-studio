variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "force_destroy" {
  description = "Allow `terraform destroy` to delete a non-empty bucket. False by default - this bucket holds user-generated project data and rendered video (docs/aws-production-architecture.md §6); an accidental destroy should fail loudly, not silently succeed."
  type        = bool
  default     = false
}

variable "tags" {
  type    = map(string)
  default = {}
}
