locals {
  name   = "${var.project_name}-${var.environment}"
  prefix = "/${var.project_name}/${var.environment}"

  # LLM provider keys (config.py's Settings class) - real values are issued
  # by each provider and MUST be set out-of-band after apply:
  #   aws ssm put-parameter --name "/ai-video-studio/production/gemini-api-key" \
  #     --type SecureString --overwrite --value "<real key>"
  # Never put real values in tfvars or any file committed to git - that's
  # exactly the plaintext-secret risk docs/aws-production-architecture.md
  # §10 moves these out of.
  llm_key_names = [
    "gemini-api-key",
    "openai-api-key",
    "groq-api-key",
    "cerebras-api-key",
    "openrouter-api-key",
  ]
}

# SSM Parameter Store (SecureString) over Secrets Manager for these -
# docs/aws-production-architecture.md §10/§12: functionally equivalent
# encryption-at-rest and IAM-gated access, free for standard parameters
# (vs. ~$0.40/secret/month), and none of these need Secrets Manager's
# rotation feature (LLM API keys aren't auto-rotated; the JWT signing key
# below is generated once by Terraform, not rotated on a schedule).
resource "aws_ssm_parameter" "llm_keys" {
  for_each = toset(local.llm_key_names)

  name  = "${local.prefix}/${each.value}"
  type  = "SecureString"
  value = "REPLACE_ME_SEE_MODULE_README"

  # Terraform creates the parameter; it must never fight an operator who
  # later sets the real value via `aws ssm put-parameter --overwrite`.
  lifecycle {
    ignore_changes = [value]
  }

  tags = merge(var.tags, { Name = "${local.name}-${each.value}" })
}

# Unlike the LLM keys, this one needs no external value - Terraform can
# safely generate it once. Replaces AUTH_SECRET_KEY's current .env-file
# default (auth/security.py has a hardcoded fallback that must never be
# used in production - this parameter is what closes that gap).
resource "random_password" "jwt_signing_key" {
  length  = 64
  special = true
}

resource "aws_ssm_parameter" "jwt_signing_key" {
  name  = "${local.prefix}/auth-secret-key"
  type  = "SecureString"
  value = random_password.jwt_signing_key.result

  tags = merge(var.tags, { Name = "${local.name}-auth-secret-key" })
}
