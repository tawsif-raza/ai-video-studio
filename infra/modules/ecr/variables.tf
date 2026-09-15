variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "image_retention_count" {
  description = "How many tagged images to keep per repository before lifecycle policy expires older ones - keeps ECR storage cost bounded."
  type        = number
  default     = 20
}

variable "tags" {
  type    = map(string)
  default = {}
}
