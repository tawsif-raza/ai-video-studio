output "instance_id" {
  value = aws_db_instance.this.identifier
}

output "endpoint" {
  value = aws_db_instance.this.endpoint
}

output "address" {
  value = aws_db_instance.this.address
}

output "port" {
  value = aws_db_instance.this.port
}

output "database_name" {
  value = aws_db_instance.this.db_name
}

output "master_user_secret_arn" {
  description = "Secrets Manager ARN RDS itself created for the master credentials (manage_master_user_password = true) - grant ECS task roles read access to exactly this secret."
  value       = aws_db_instance.this.master_user_secret[0].secret_arn
}
