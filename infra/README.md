# AI Video Studio — AWS Infrastructure (Terraform)

Implements `docs/aws-production-architecture.md`. Read that document first — this README covers how to actually drive the Terraform, not why the architecture looks the way it does.

## Status: plan-reviewed, not applied

This has been through `terraform init` / `terraform validate` (both clean) and is intended to go through `terraform plan` for review before anyone runs `terraform apply`. **Do not apply until you've read the "Before you apply" section below** — three of the fourteen resource groups this stack creates are infrastructure for application code that does not exist yet.

## Layout

```
infra/
├── modules/            # one concern per module, no module calls another
│   ├── networking/      VPC, subnets, NAT, route tables, VPC endpoints
│   ├── security_groups/ ALB / API / worker / RDS security groups
│   ├── s3/               media bucket (KMS, versioning, public-access-blocked)
│   ├── sqs/              jobs queue + DLQ
│   ├── secrets/          SSM SecureString params (LLM keys, JWT signing key)
│   ├── ecr/               one repo (API and worker share an image - see §9)
│   ├── logging/          CloudWatch log groups + the alerts SNS topic
│   ├── iam/               task execution role + 2 task roles (API, worker)
│   ├── rds/               PostgreSQL, RDS-managed master credentials
│   ├── dns/               Route 53 zone (optional) + ACM cert (optional)
│   ├── alb/               ALB, HTTPS/HTTP listeners, API target group
│   ├── ecs_cluster/      shared ECS cluster (Fargate + Fargate Spot)
│   ├── ecs_api/           API service, task def, target-tracking autoscaling
│   ├── ecs_worker/       worker service, task def, SQS-backlog autoscaling
│   └── alarms/            the CloudWatch alarms that need late-bound IDs
│                          (ALB/ECS/RDS ARNs) - kept separate from logging/
│                          to avoid a module dependency cycle
└── environments/
    └── production/       the only environment right now - wires every
                          module together with real values
```

Why `alarms` is split from `logging`: alarms need the ALB, ECS services, and RDS instance to already exist (to reference their ARNs/names as alarm dimensions); those services need `logging`'s log groups to exist first (for their task definitions). One `monitoring` module trying to do both would be a dependency cycle - two smaller modules aren't.

## Before you apply

**Three prerequisite application code changes have not landed yet** (`docs/aws-production-architecture.md`'s closing section):

1. **S3-backed storage** — the app currently writes to local disk (`OUTPUT_DIR`). Fargate has no persistent local disk; without this, every project is lost on the first task replacement.
2. **RDS-backed `RunRegistry` and user store** — the app currently keeps run state and user accounts in-memory/on local disk, single-process only. `modules/ecs_api`'s `min_capacity` defaults to 1 specifically because of this — **do not raise it** until this migration lands, or you reproduce the exact bug already documented for the existing Railway deployment (SSE progress and run-status lookups silently break for requests landing on a different task).
3. **The worker split** — `modules/ecs_worker`'s task definition runs `python worker.py`, a file that **does not exist in the codebase yet**. It needs to be the SQS poll loop described in `docs/aws-production-architecture.md` §4, dispatching to the existing, unmodified `run_director_pipeline`/`run_producer_pipeline`/`run_render_pipeline`/`run_publish_pipeline` functions.

This Terraform is written correctly for the target architecture *once those land*. Applying it before they do will provision working infrastructure around an application that isn't ready to use it — the ECS services will either crash-loop (`worker.py` genuinely doesn't exist) or run in a degraded, silently-lossy mode (API on ephemeral Fargate storage). **`ecs_worker`'s `min_capacity` defaults to 0 for exactly this reason** — it's safe to `apply` with the worker service sitting at zero tasks while those three changes land, then raise it once `worker.py` exists.

## Secrets — populated out-of-band, never in tfvars

`modules/secrets` creates SSM SecureString parameters with a `REPLACE_ME_SEE_MODULE_README` placeholder value for every LLM provider key. **Terraform never sees or stores the real key values** — populate them after `apply`, from a terminal with your own AWS credentials, never from a value in this repo:

```bash
aws ssm put-parameter --name "/ai-video-studio/production/gemini-api-key" \
  --type SecureString --overwrite --value "<real key>"
# repeat for openai-api-key, groq-api-key, cerebras-api-key, openrouter-api-key
```

The JWT signing key (`auth-secret-key`) is the one exception — Terraform generates it itself (`random_password`) since, unlike a provider-issued API key, there's no external value it needs to match.

RDS's master password is handled even more simply: `manage_master_user_password = true` means **RDS itself** creates and owns that secret in Secrets Manager. Terraform never generates, sees, or stores it at all.

## Bootstrapping AWS CLI access

This environment authenticates via `aws login` (console-credential browser login, not IAM Identity Center SSO or long-lived access keys) — run it yourself whenever the session expires:

```
aws login
```

## Running a plan

```bash
cd infra/environments/production
cp terraform.tfvars.example terraform.tfvars   # then edit it
terraform init
terraform plan -out=plan.tfplan
terraform show plan.tfplan   # review in full before ever applying
```

Review the plan against the checklist in `docs/aws-production-architecture.md`'s companion review (or just re-read this repo's own commit/PR history for it) before running `terraform apply plan.tfplan` — specifically: no public database, no `0.0.0.0/0` security group ingress beyond the ALB's 80/443, no IAM `Resource: "*"` beyond the two AWS actions that structurally require it (`ecr:GetAuthorizationToken`, and KMS `Decrypt` scoped via a `kms:ViaService`-style condition or a specific key ARN — this stack uses the latter), encryption enabled on RDS/S3/SQS/CloudWatch Logs/SNS, `deletion_protection` on for RDS, and the S3 bucket's public access block intact.

## State

Local backend for now (`environments/production/providers.tf`) — deliberate, not an oversight: an S3 backend needs a bucket to exist before this stack can use it, which is a bootstrapping problem for the very first apply. Once this stack has been applied once, consider migrating to an S3 backend (Terraform ≥ 1.10 supports native S3 locking via `use_lockfile`, no DynamoDB table needed) using one of the buckets this stack could reasonably own, or a small separate bootstrap stack.

## What this does NOT include yet

- The GitHub Actions deploy pipeline (`docs/aws-production-architecture.md` §9) - OIDC role + workflow file. Not infrastructure this Terraform provisions by itself in scope for this pass; add as a follow-up (the OIDC provider + deploy role are straightforward additions to `modules/iam` when that's ready).
- CloudFront in front of the S3 bucket - explicitly deferred per the cost strategy (§12) until there's real video-serving traffic to optimize.
- WAF on the ALB - called for in the architecture doc (§10) but not yet added to `modules/alb`; a reasonable near-term follow-up, especially before opening `/auth/login` to real traffic.
