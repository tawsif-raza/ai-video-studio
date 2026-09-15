variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "log_retention_days" {
  description = "docs/aws-production-architecture.md §8/§12: bounded, not indefinite - unbounded log retention is a real, easy-to-miss cost leak."
  type        = number
  default     = 60
}

variable "alarm_email" {
  description = "Optional email subscribed to the alerts SNS topic. Leave empty to create the topic without a subscription (wire it up to Slack/PagerDuty/etc. separately)."
  type        = string
  default     = ""
}

variable "tags" {
  type    = map(string)
  default = {}
}
