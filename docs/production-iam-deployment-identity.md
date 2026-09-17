# Production Deployment Identity — Plan (not yet executed)

**Status:** documented plan only. No IAM entity has been created or modified. Written in response to the finding that `terraform plan` for `infra/environments/production/` was run authenticated as the AWS account **root user**, which must not be used for `terraform apply`.

## Why not root

Root has unconstrained access to every resource and every billing/account-level action in `801702847930`, with no permissions boundary and no scoping possible. A single leaked or misused root credential is a total-account-compromise event. Terraform only ever needs a specific, enumerable set of provisioning permissions (below) — root grants it that and everything else, which violates least privilege by construction, independent of how carefully the Terraform code itself is written.

## Why not federation / IAM Identity Center (the task's own first-choice option)

No AWS SSO / IAM Identity Center instance exists in this account (`aws sso-admin list-instances` → `{"Instances": []}`). Standing one up is a real, separate organizational decision (it changes how *every* future user signs in to this account, not just this deployment) — out of scope to do silently as a side effect of this Terraform review. Flagged as a reasonable future upgrade, not proposed for immediate action.

## Recommended: a dedicated, least-privilege IAM user

Audited the account's existing IAM users first, to avoid creating a redundant one:

| User | Attached policies | Suitable? |
|---|---|---|
| `Tawsif-admin` | `AdministratorAccess`, `IAMUserChangePassword`, `AmazonBedrockFullAccess` | No — same over-broad problem as root, just one level down |
| `Tawsif-Raza` | **none** (zero attached, zero inline, zero access keys, zero console login profile, zero MFA) | **Yes** — bare, currently unused, no risk of disrupting whatever else it might otherwise be for, since it's not being used for anything today |
| `FInal_ac`, `MantleApiKey-*` | not inspected | Out of scope — names suggest unrelated projects |

**Recommendation: scope `Tawsif-Raza` down for this purpose, rather than create a new IAM user.** Fewer IAM entities to track, and it starts from zero permissions rather than needing anything stripped away from an identity already used for something else.

## Recommended permission model

Two policies, attached together — deliberately not one big custom policy, so the IAM-specific (most sensitive) part stays small, readable, and separately auditable from the "everything else Terraform provisions" part:

### 1. AWS-managed `PowerUserAccess`

Grants the S3/SQS/RDS/ECS/ECR/EC2(VPC+SGs)/ELB/CloudWatch/Application-Auto-Scaling/KMS/SSM/SNS/Route53/ACM actions this stack's 14 modules need to create every resource type it declares (enumerated directly from source — see "Resource types this stack manages" below), **except** IAM itself — `PowerUserAccess` explicitly carves IAM (and Organizations/Account) out by design, which is exactly the separation this task asked for ("infrastructure provisioning identity" vs. "IAM management" not being the same blast radius).

### 2. A small custom policy — only the IAM actions Terraform needs, only on this project's roles

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ManageAppRuntimeRoles",
      "Effect": "Allow",
      "Action": [
        "iam:CreateRole",
        "iam:DeleteRole",
        "iam:GetRole",
        "iam:UpdateRole",
        "iam:UpdateAssumeRolePolicy",
        "iam:TagRole",
        "iam:UntagRole",
        "iam:ListRoleTags",
        "iam:PutRolePolicy",
        "iam:GetRolePolicy",
        "iam:DeleteRolePolicy",
        "iam:ListRolePolicies",
        "iam:AttachRolePolicy",
        "iam:DetachRolePolicy",
        "iam:ListAttachedRolePolicies"
      ],
      "Resource": "arn:aws:iam::801702847930:role/ai-video-studio-*"
    },
    {
      "Sid": "PassRuntimeRolesToEcsOnly",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::801702847930:role/ai-video-studio-*",
      "Condition": {
        "StringEquals": { "iam:PassedToService": "ecs-tasks.amazonaws.com" }
      }
    }
  ]
}
```

Resource-scoped to `role/ai-video-studio-*` only — covers both `ai-video-studio-staging-*` (so this identity can also manage staging without breaking it — "do not break staging" was explicit) and `ai-video-studio-production-*`. Cannot touch `Tawsif-admin`, `Tawsif-Raza` itself, `ecsTaskExecutionRole`, or any other role in the account. `PassRole` further conditioned so these roles can only ever be handed to `ecs-tasks.amazonaws.com` — not to some other service as a privilege-escalation path.

This pairing is standard, well-understood AWS practice (not a hand-rolled fine-grained policy per resource type, which risks missing an action and breaking `apply` partway through, or over/under-scoping by guesswork) — `PowerUserAccess` for the provisioning breadth, a narrow custom policy for the one category it deliberately excludes.

## No long-lived access keys

`Tawsif-Raza` currently has zero access keys and no console login profile. Plan:

1. Enable a console login profile for `Tawsif-Raza` (a password, not an access key).
2. Attach the two policies above.
3. Next `aws login`, select the `Tawsif-Raza` console session in the browser instead of root — the CLI caches short-lived, auto-refreshing temporary credentials for *that* identity, the same mechanism already in use today, just pointed at a scoped, non-root identity instead of root.

This avoids creating any long-lived programmatic access key at all, which is a stronger posture than the task's hard rule strictly required (it only forbade long-lived **root** keys).

## Resource types this stack manages (what the permission model above must cover)

Enumerated directly from `infra/modules/*/main.tf` and `infra/environments/production/main.tf` — not guessed:

`aws_vpc`, `aws_subnet`, `aws_internet_gateway`, `aws_nat_gateway`, `aws_eip`, `aws_route_table`, `aws_route`, `aws_route_table_association`, `aws_security_group`, `aws_security_group_rule`, `aws_vpc_endpoint`, `aws_lb`, `aws_lb_listener`, `aws_lb_target_group`, `aws_acm_certificate`, `aws_acm_certificate_validation`, `aws_route53_zone`, `aws_route53_record`, `aws_ecs_cluster`, `aws_ecs_cluster_capacity_providers`, `aws_ecs_service`, `aws_ecs_task_definition`, `aws_appautoscaling_target`, `aws_appautoscaling_policy`, `aws_db_instance`, `aws_db_subnet_group`, `aws_s3_bucket` (+ its sub-resources), `aws_sqs_queue`, `aws_sqs_queue_redrive_allow_policy`, `aws_ssm_parameter`, `aws_ecr_repository`, `aws_ecr_lifecycle_policy`, `aws_cloudwatch_log_group`, `aws_cloudwatch_metric_alarm`, `aws_kms_key`, `aws_kms_alias`, `aws_sns_topic`, `aws_sns_topic_subscription`, `aws_iam_role`, `aws_iam_role_policy`, `aws_iam_role_policy_attachment`, `random_password`.

Every one of these except the `aws_iam_*` types and `iam:PassRole` is covered by `PowerUserAccess`; the `aws_iam_*` types and `PassRole` are covered by the custom policy above.

## What this does NOT change

- The **application runtime roles** this stack creates (`api-task`, `worker-task`, `ecs-execution`) are unaffected — they're what the *running containers* use, already reviewed and confirmed least-privilege in `docs/production-terraform-review.md`. This document is about the separate identity a *human* uses to run `terraform apply`, not about those roles.
- Staging is not modified by this plan — `Tawsif-Raza` would gain the *ability* to manage `ai-video-studio-staging-*` resources (same as it would for production), but nothing about staging's existing resources or state changes until someone actually runs Terraform against staging with this identity.

## Execution steps (require explicit authorization — not run yet)

1. `aws iam create-login-profile --user-name Tawsif-Raza --password <generated>` (or equivalent console action) — enables password/console sign-in, no access key.
2. `aws iam attach-user-policy --user-name Tawsif-Raza --policy-arn arn:aws:iam::aws:policy/PowerUserAccess`
3. `aws iam put-user-policy --user-name Tawsif-Raza --policy-name ai-video-studio-terraform-iam --policy-document file://<the JSON above>`
4. You sign in to the AWS Console once as `Tawsif-Raza` (sets the console session `aws login` will offer).
5. `aws login` → select the `Tawsif-Raza` session instead of root.
6. `aws sts get-caller-identity` → confirm principal is `arn:aws:iam::801702847930:user/Tawsif-Raza`, not root.
