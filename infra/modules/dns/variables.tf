variable "domain_name" {
  description = "e.g. api.yourdomain.com. Empty string skips this module entirely (no Route 53 zone, no ACM cert) - the ALB then gets an HTTP-only listener (see modules/alb) until a domain is ready."
  type        = string
  default     = ""
}

variable "create_zone" {
  description = "True to create a new Route 53 hosted zone for a root/apex domain you're delegating to AWS. False to use an existing zone (e.g. the domain's apex is managed elsewhere and you're only adding a record for a subdomain) - set zone_id in that case."
  type        = bool
  default     = false
}

variable "zone_id" {
  description = "Existing Route 53 hosted zone ID, used when create_zone = false."
  type        = string
  default     = ""
}

variable "tags" {
  type    = map(string)
  default = {}
}
