variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "visibility_timeout_seconds" {
  description = "Must stay comfortably above the application's PIPELINE_TIMEOUT_SECONDS (config.py, default 1800s) so SQS never redelivers a message while a worker is still legitimately processing it (docs/aws-production-architecture.md §7)."
  type        = number
  default     = 2100
}

variable "max_receive_count" {
  description = "Attempts before a message moves to the DLQ instead of retrying forever (docs/aws-production-architecture.md §7 - directly closes the 'unbounded retries' resource risk from the stability audit)."
  type        = number
  default     = 3
}

variable "message_retention_seconds" {
  type    = number
  default = 345600 # 4 days
}

variable "tags" {
  type    = map(string)
  default = {}
}
