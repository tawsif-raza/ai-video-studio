output "certificate_arn" {
  value = local.enabled ? aws_acm_certificate_validation.this[0].certificate_arn : ""
}

output "zone_id" {
  value = local.zone_id
}
