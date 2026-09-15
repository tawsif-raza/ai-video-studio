output "alb_dns_name" {
  value = module.alb.alb_dns_name
}

output "app_url" {
  value = var.domain_name != "" ? "https://${var.domain_name}" : "http://${module.alb.alb_dns_name}"
}

output "ecr_repository_url" {
  value = module.ecr.repository_url
}

output "s3_bucket_name" {
  value = module.s3.bucket_id
}

output "sqs_queue_url" {
  value = module.sqs.queue_url
}

output "sqs_dlq_url" {
  value = module.sqs.dlq_url
}

output "rds_endpoint" {
  value = module.rds.endpoint
}

output "rds_master_secret_arn" {
  description = "Where the RDS-managed master credentials live in Secrets Manager - never printed in plaintext by Terraform."
  value       = module.rds.master_user_secret_arn
}

output "sns_alerts_topic_arn" {
  value = module.logging.alerts_topic_arn
}

output "llm_key_parameter_names" {
  description = "SSM parameter names to populate post-apply - see infra/README.md."
  value       = module.secrets.llm_key_parameter_names
}
