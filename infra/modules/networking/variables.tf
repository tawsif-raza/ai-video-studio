variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "azs" {
  description = "Exactly 2 AZs, per docs/aws-production-architecture.md §2 - HA requires 2, and a 3rd isn't justified at this app's scale."
  type        = list(string)

  validation {
    condition     = length(var.azs) == 2
    error_message = "Exactly 2 availability zones are expected (see docs/aws-production-architecture.md §2)."
  }
}

variable "enable_second_nat_gateway" {
  description = <<-EOT
    Cost-control default is false (docs/aws-production-architecture.md §2/§12):
    the worker service is the only thing behind NAT (it calls external LLM
    providers), and it already retries across 5 providers on failure via
    FailoverLLMClient - AZ-level NAT redundancy is a smaller reliability gain
    than its ~$33/month duplicate cost for this specific workload. Flip this
    on only if a single NAT Gateway is an observed problem, not preemptively.
  EOT
  type        = bool
  default     = false
}

variable "create_interface_endpoints" {
  description = <<-EOT
    Default true (unchanged behavior). AWS bills each interface endpoint
    per-AZ, not per-endpoint - with 2 AZs this module's 6 endpoints
    (sqs/secretsmanager/ssm/logs/ecr.api/ecr.dkr) cost ~$87.60/month, not
    the ~$43.80/month a per-endpoint reading suggests. Set false to delete
    them and route that traffic over the NAT Gateway instead (requires the
    caller to also allow the API task internet egress, e.g.
    api_allow_internet_egress=true) - the same pattern staging's
    terraform.tfvars already runs in production today. The free S3 gateway
    endpoint (aws_vpc_endpoint.s3) is unaffected either way.
  EOT
  type        = bool
  default     = true
}

variable "tags" {
  type    = map(string)
  default = {}
}
