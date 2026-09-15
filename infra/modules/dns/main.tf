locals {
  enabled = var.domain_name != ""
}

resource "aws_route53_zone" "this" {
  count = local.enabled && var.create_zone ? 1 : 0
  name  = var.domain_name
  tags  = var.tags
}

locals {
  zone_id = local.enabled ? (var.create_zone ? aws_route53_zone.this[0].zone_id : var.zone_id) : ""
}

resource "aws_acm_certificate" "this" {
  count             = local.enabled ? 1 : 0
  domain_name       = var.domain_name
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = var.tags
}

resource "aws_route53_record" "cert_validation" {
  for_each = local.enabled ? {
    for dvo in aws_acm_certificate.this[0].domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  } : {}

  zone_id         = local.zone_id
  name            = each.value.name
  type            = each.value.type
  ttl             = 300
  records         = [each.value.record]
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "this" {
  count                   = local.enabled ? 1 : 0
  certificate_arn         = aws_acm_certificate.this[0].arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
}

# The ALB alias record is deliberately NOT in this module - it would create
# a cycle (this module would need the ALB's DNS name, but the ALB needs
# this module's certificate_arn for its HTTPS listener). The root module
# creates that one record directly once both this module and modules/alb
# have run - see environments/production/main.tf.
