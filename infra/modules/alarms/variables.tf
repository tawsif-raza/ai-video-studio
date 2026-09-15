variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "sns_topic_arn" {
  type = string
}

variable "alb_arn_suffix" {
  type = string
}

variable "api_target_group_arn_suffix" {
  type = string
}

variable "sqs_queue_name" {
  type = string
}

variable "sqs_dlq_name" {
  type = string
}

variable "rds_instance_id" {
  type = string
}

variable "ecs_cluster_name" {
  type = string
}

variable "ecs_api_service_name" {
  type = string
}

variable "ecs_worker_service_name" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
