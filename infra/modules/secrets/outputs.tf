output "llm_key_parameter_arns" {
  value = { for k, v in aws_ssm_parameter.llm_keys : k => v.arn }
}

output "llm_key_parameter_names" {
  value = { for k, v in aws_ssm_parameter.llm_keys : k => v.name }
}

output "jwt_signing_key_parameter_arn" {
  value = aws_ssm_parameter.jwt_signing_key.arn
}

output "jwt_signing_key_parameter_name" {
  value = aws_ssm_parameter.jwt_signing_key.name
}
