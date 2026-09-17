# Production Terraform Review

**Reviewed:** 2026-09-15 (refreshed same day, after AWS re-authentication)
**Scope:** `infra/environments/production/` — inspection, validation, plan generation, and analysis only. **No `terraform apply` was run in either pass of this review.** No AWS resource was created, modified, or destroyed.

> This is the second pass of this review. The first pass (same date, earlier) returned **DO NOT APPLY** because AWS credentials were expired and the only plan file on disk predated a real security-group fix. This pass re-authenticates, archives that stale plan, resolves every blocker that could be resolved without inventing information, and generates a verified fresh plan. **The final decision below remains DO NOT APPLY**, by explicit instruction, until the still-open items (no production domain, no alarm email, no real container image yet) are resolved in a further, separate pass.

## AWS Account

**801702847930**, region **ap-south-1** — confirmed live this pass:

```
$ aws sts get-caller-identity
{
    "UserId": "801702847930",
    "Account": "801702847930",
    "Arn": "arn:aws:iam::801702847930:root"
}
```

Matches the account ID previously recovered indirectly from the stale plan's S3 bucket name — now independently confirmed live, not inferred.

**Finding:** the authenticated principal is the **AWS account root user** (`arn:aws:iam::801702847930:root`), not an IAM user or role. This is usable for this review's read-only `plan` step, but running `terraform apply` against production as root is against AWS best practice — no least-privilege boundary, no scoped permissions, maximum blast radius if these credentials are ever compromised. Carried into Security Findings below; not fixed here (it's the account's existing configured access, not something this review's scope changes).

**Credential-chain note (process transparency, not a security issue):** `aws sts get-caller-identity` succeeds via the AWS CLI's own `aws login` browser-based session cache (`~/.aws/config`'s `login_session` key — no static keys in `~/.aws/credentials`). Terraform's AWS provider uses an independent (Go SDK) credential chain that does not recognize that cache format, and failed with `No valid credential sources found` on the first plan attempt this pass. Resolved by running `aws configure export-credentials --format env` (a standard, supported AWS CLI command for exactly this interop case) and sourcing its output into the shell environment for the `terraform plan` command only — nothing was written into any `.tf`/`.tfvars` file, no secret was printed to output, and the temporary env file was deleted immediately after use.

## AWS Region

**ap-south-1** — confirmed via `aws configure get region` and consistent throughout `terraform.tfvars`/`variables.tf`.

## Terraform Validation

```
terraform fmt -recursive        → fixed 1 pre-existing cosmetic alignment diff (modules/networking/main.tf, whitespace only, no functional change)
terraform fmt -check -recursive → clean (exit 0)
terraform validate              → Success! The configuration is valid.
```

`git status`/`git diff` reviewed before generating the plan (per this task's own gate) — only the intentional changes made during this review were present (see "Changes Made This Pass" below) plus one pre-existing, unrelated tracked `.pyc` binary diff (build artifact, not part of this engagement). No unexpected repository changes.

## Changes Made This Pass

To resolve as many launch blockers as could be resolved without inventing information:

1. **`infra/environments/production/terraform.tfvars`** (gitignored, not committed):
   - `cors_origins`: placeholder → `https://ai-video-studio-dashboard.vercel.app` (the app's own canonical production alias — hardcoded into `web_api/__init__.py`'s `_VERCEL_PREVIEW_ORIGIN_RE` as the production origin, not invented).
   - `alb_ingress_cidrs` (new): `["49.205.150.163/32", "157.45.192.76/32"]` — the same two operator CIDRs already used for staging's controlled validation. **Compensating control** for the fact that no HTTPS exists yet: without this, the default (`0.0.0.0/0`) would expose an HTTP-only ALB — carrying auth tokens and cookies in plaintext — to the entire internet.
   - `image_tag`: unset (placeholder) → `sha-211daae` (current `HEAD` short SHA — deterministic, not `latest`). **This does not mean an image exists in ECR under this tag** — the ECR repo itself is one of the resources this same apply would create, so nothing could have been pushed to it yet. Documented inline in the tfvars comment; real verification (`aws ecr describe-images`) has to happen after apply, before raising `desired_count`.
   - `alarm_email`: left empty — pending, not yet provided.
   - `domain_name`/`create_dns_zone`/`existing_dns_zone_id`: **left empty, unchanged, by explicit instruction.** No domain exists; none was invented; HTTPS/ACM/Route 53 remain fully disabled and parameterized, not partially wired.
2. **`infra/environments/production/variables.tf`**: added `alb_ingress_cidrs` and `api_allow_internet_egress` variable declarations (previously only declared in staging's `variables.tf`, with production silently falling through to the module's own defaults — `0.0.0.0/0` and `false` respectively). Production needed an explicit variable to actually override the ALB CIDR default; `api_allow_internet_egress` was added alongside it for consistency (kept at `false`, matching the module default — no behavior change, just makes the choice explicit and documented rather than implicit).
3. **`infra/environments/production/main.tf`**: passes both new variables through to `module.security_groups`.
4. **`infra/modules/networking/main.tf`**: `terraform fmt` whitespace fix only (see Terraform Validation).
5. **Archived** the stale plan: `plan.tfplan` (2026-09-13, predating the SG fix) → renamed to `stale-20260913-pre-sg-fix.tfplan` so it cannot be accidentally applied under its original, README-documented filename. Still gitignored, not committed, kept only for audit trail.

None of this touches `infra/modules/security_groups/`, `infra/modules/alb/`, or `infra/modules/dns/` — the security-group fix and the domain/HTTPS gating logic were already correct; only environment-level wiring (tfvars + the two missing variable pass-throughs) changed.

## Plan Summary

**A complete, fresh, credentialed `terraform plan` was generated successfully this pass:**

```
Plan: 90 to add, 0 to change, 0 to destroy.
```

(93 total plan entries: 90 creates + 3 data-source reads.) Verified via `terraform show -json` — the only two action types present anywhere in the plan are `create` and `read`; zero `update`, zero `delete`, zero `replace`. Consistent with production having no existing Terraform state (confirmed: no `terraform.tfstate` in `infra/environments/production/`) — this is a from-scratch stack.

**Diffed directly against the stale plan** to confirm the security-group fix (and a related networking fix) actually shows up in real plan output, not just in source review:

| Resource | Stale plan (2026-09-13, pre-fix) | Fresh plan (this pass) |
|---|---|---|
| `module.security_groups.aws_security_group_rule.api_to_vpc_endpoints` | **absent** | present (create) |
| `module.security_groups.aws_security_group_rule.worker_to_internet` | **absent** | present (create) |
| `module.networking.aws_vpc_endpoint.interface["ssm"]` | **absent** | present (create) |
| `module.networking.aws_vpc_endpoint.interface["ecr.api"]` | **absent** | present (create) |
| `module.networking.aws_vpc_endpoint.interface["ecr.dkr"]` | **absent** | present (create) |
| Everything else (85 resources) | present | present, unchanged in kind |

No resource present in the stale plan is absent from the fresh one — this is purely additive (the fix adds rules/endpoints; it removes nothing). The fresh plan is confirmed current against `HEAD` (`211daae`).

**Spot-checked configuration values baked into the plan** (via `terraform show -json`'s variable/resource `after` values, not assumed):
- ALB security group ingress: `cidr_blocks = ["49.205.150.163/32", "157.45.192.76/32"]` on both 80 and 443 — confirmed **not** `0.0.0.0/0`.
- `module.security_groups.aws_security_group_rule.api_to_internet`: **absent from the plan** (count=0, since `api_allow_internet_egress=false`) — correct, the API needs no direct internet egress now that the worker split exists in code.
- Root module variables: `cors_origins = "https://ai-video-studio-dashboard.vercel.app"`, `image_tag = "sha-211daae"`, `domain_name = ""`, `alarm_email = ""`.
- `module.dns` and `module.alb.aws_lb_listener.https`: **zero resources planned** — confirmed no ACM/Route 53/HTTPS listener is being created, matching the explicit "keep disabled, don't invent a domain" instruction. Only `aws_lb.this`, `aws_lb_target_group.api`, and `aws_lb_listener.http` exist under `module.alb`.

## Resources To Create (90, by module)

| Module | Count | Notes |
|---|---|---|
| `networking` | 24 | VPC, IGW, 2 public + 2 private subnets, 1 NAT Gateway + EIP, route tables/associations, VPC endpoints SG, S3 gateway endpoint, **6** interface endpoints (`sqs`, `secretsmanager`, `logs`, `ssm`, `ecr.api`, `ecr.dkr`) |
| `security_groups` | 8 | ALB/API/worker/RDS SGs + `api_to_vpc_endpoints`, `api_to_rds`, `worker_to_internet`, `worker_to_rds` (no `api_to_internet` — correctly absent) |
| `s3` | 9 | Media bucket + ownership controls, public access block, versioning, SSE-KMS + KMS key/alias, lifecycle rules, TLS-only bucket policy |
| `sqs` | 3 | Jobs queue, DLQ, redrive-allow policy |
| `secrets` | 7 | 5 SSM SecureString LLM-key parameters (placeholder values), JWT signing key (`random_password` + its SSM parameter) |
| `ecr` | 2 | Repository + lifecycle policy |
| `logging` | 4 | API + worker log groups, logs KMS key, alerts SNS topic |
| `iam` | 10 | Execution role + policy + managed attachment, API task role + policy, worker task role + policy, 3 policy-document data reads |
| `rds` | 3 | Subnet group, KMS key, `db.t4g.micro` PostgreSQL 16 instance |
| `alb` | 3 | Load balancer, target group, **HTTP listener only** |
| `ecs_cluster` | 2 | Cluster + capacity providers |
| `ecs_api` | 4 | Task definition, service (`desired_count=1`), autoscaling target + CPU policy |
| `ecs_worker` | 7 | Task definition, service (`desired_count=0`, Fargate Spot), autoscaling target, scale-in/out policies, 2 SQS-backlog alarms |
| `alarms` | 7 | ALB unhealthy hosts, API CPU high, DLQ has-messages, queue backlog age, RDS CPU high, RDS free-storage low, worker memory high |
| `dns` | 0 | No domain configured — correctly creates nothing |

## Resources To Update

**None.** No existing production state.

## Resources To Replace

**None.**

## Resources To Destroy

**None.**

## Potentially Destructive Actions

**None for this apply** (nothing exists to destroy or replace on a from-scratch stack). Forward-looking safeguards already in place for *future* applies, confirmed present in the fresh plan's resource configuration: `aws_s3_bucket.media` has `force_destroy=false`; `aws_db_instance.this` has `deletion_protection=true` and `skip_final_snapshot=false`; ALB/security groups use `create_before_destroy=true`.

## Security Findings

1. **No HTTPS — by design, this pass, per explicit instruction.** ALB is HTTP-only (no ACM cert, no `domain_name`). **Compensating control added this pass:** ALB ingress restricted to 2 operator CIDRs (was defaulting to `0.0.0.0/0`) — auth tokens/cookies can still only reach this environment from those two networks, not the public internet, while it remains HTTP-only. This satisfies "do not weaken security because a domain is unavailable" but does **not** make this environment safe for real end-user traffic — see "Blocked only by the missing domain" below.
2. **Root-user credentials** used for this plan (see AWS Account). Not fixed in this pass; flagged for whoever runs the eventual `apply` to use a scoped IAM role/user instead.
3. **No WAF on the ALB** — documented, deferred gap (architecture doc §10, `infra/README.md`), unchanged this pass.
4. **IAM remains well-scoped** — reconfirmed in the fresh plan: the only `Resource: "*"` statements are `ecr:GetAuthorizationToken` (structurally required by AWS) and `kms:Decrypt` scoped by `kms:ViaService` condition to AWS-managed SSM/Secrets Manager keys only. No wildcard actions.
5. **Encryption/public-access posture unchanged and confirmed**: RDS not publicly accessible, storage-encrypted; S3 fully public-access-blocked, KMS-encrypted, TLS-only bucket policy; SQS SSE-enabled; CloudWatch Logs KMS-encrypted.
6. **Secrets**: RDS master password never touches Terraform state (RDS-managed); JWT signing key generated by Terraform but only ever injected via SSM parameter ARN at container start; LLM keys are placeholder SSM parameters requiring an out-of-band `aws ssm put-parameter` after apply (documented in `infra/README.md`, unchanged this pass).

## High Availability Findings

Unchanged from the first pass's findings — re-confirmed present in the fresh plan:
- API `desired_count=1` (RDS-backed RunRegistry has landed in code, making a raise to 2 safe/recommended but not required).
- Worker isolated from API (separate service/SG/task role); autoscales 0→10 on SQS backlog, scale-in after 15 min empty.
- RDS Single-AZ (deliberate cost tradeoff, automated backups + PITR still apply).
- No ECS deployment circuit breaker (not a launch requirement per architecture doc §11; a stuck bad deploy needs manual cancellation, but a bad deploy can't cause an outage under the current `minimumHealthyPercent=100` rolling config).
- 2-AZ subnet/RDS spread; single NAT Gateway (documented single point of failure for worker *outbound* only).

## Cost Findings

Unchanged in shape from the first pass (no sizing variables were touched this pass) — directionally ~$85-160/month at low traffic per the architecture doc's own §11 estimate, not re-priced here. Ranked as requested:

1. **RDS** (`db.t4g.micro`, Single-AZ, 20GB gp3) — small fixed cost (~$15/mo class), the safety-critical piece, not oversized.
2. **ECS API** (0.5 vCPU/1GB, 1-4 tasks, on-demand Fargate — never Spot, correctly, since it's user-facing) — usage-scaling, starts at `desired_count=1`.
3. **ECS worker** (1 vCPU/2GB, 0-10 tasks, **Fargate Spot enabled** for ~70% savings) — genuinely usage-proportional, scales to **zero** tasks when idle; this is the largest *variable* cost driver but also the most cost-optimized (Spot + scale-to-zero both already on).
4. **NAT Gateway** (1, not 2) — fixed cost regardless of traffic; already minimized per architecture doc §12's own reasoning (worker retries across 5 LLM providers, so AZ-level NAT redundancy isn't worth 2x the cost here).
5. **ALB** — fixed hourly + LCU usage; unavoidable, one ALB is the minimum for this architecture.
6. **CloudWatch** — log retention capped at 60 days (not indefinite), 7 alarms (negligible alarm cost itself, cost is dominated by log ingestion/storage volume which scales with traffic).
7. **S3** — cheap at this app's scale (~$0.023/GB-month), lifecycle rules bound multipart-upload and old-version accumulation.
8. **Data transfer** — not independently estimable without real traffic; NAT Gateway data processing and ALB-to-internet egress are the two components that would show up here once traffic is real.

No unnecessary services introduced this pass (CloudFront and WAF remain correctly deferred). No compute was resized. No expensive option was enabled without existing justification already documented in the architecture doc.

## Monitoring Findings

- 7 CloudWatch alarms confirmed present in the fresh plan, matching architecture doc §8.
- **SNS topic still has no email subscription** — `alarm_email` remains empty, pending. Every alarm fires into a zero-subscriber topic until this is set.

## Rollback Findings

Unchanged from the first pass: ECS task definitions versioned automatically; no circuit breaker (manual rollback of a stuck bad deploy); `image_tag` is deliberately a value that won't resolve to a real image until one is built and pushed (see "Changes Made This Pass" #1); Terraform state remains local/unlocked (documented, deliberate bootstrapping choice, real risk for a multi-operator team — unchanged recommendation to migrate to an S3 backend once this stack exists).

## Staging vs Production Differences

Re-verified this pass, now including the two new production-only variables added:

| Setting | Staging | Production |
|---|---|---|
| `alb_ingress_cidrs` | `["49.205.150.163/32", "157.45.192.76/32"]` (tfvars) | **Now also** `["49.205.150.163/32", "157.45.192.76/32"]` (tfvars, added this pass) — same operator CIDRs, both environments equally locked down for now; production's is a temporary pre-HTTPS posture, staging's is permanent-until-its-own-review per its existing comment |
| `api_allow_internet_egress` | `true` (temporary escape hatch) | `false` (explicit now, was implicit via module default before this pass) |
| `use_fargate_spot_for_worker` | `false` | `true` (module default, unchanged) |
| `cors_origins` | `http://localhost:3000` (test-harness value) | `https://ai-video-studio-dashboard.vercel.app` (real value, set this pass) |
| `domain_name` | empty | empty — **unchanged, by explicit instruction, no domain invented** |
| Terraform state | Applied, exists | Still no state — this plan has not been applied |

Resource naming: `local.name = "${project_name}-${environment}"` throughout every module — reconfirmed no staging/production resource-name collision in the fresh plan's 90 planned resource names.

**Outstanding from the first-pass review, not addressed this pass (out of this pass's requested scope — staging file, not production):** `infra/environments/staging/variables.tf`'s own `environment` variable still defaults to `"production"` (a copy-paste artifact; staging's real `terraform.tfvars` overrides it correctly, so no live impact, but the wrong default remains a latent risk if staging is ever re-planned without its tfvars). Still recommended, still not required, still not fixed.

## Classification (as requested)

### 1. What is ready now
- Networking, security groups (including the fix), S3, SQS/DLQ, RDS, IAM, ECS cluster/API/worker service definitions, ECR, logging, and alarms are all correctly configured and produce a clean, verified, zero-destroy/zero-replace plan.
- The security-group egress fix from staging is present and confirmed in the live plan output for production (not just source-reviewed).
- CORS is set to the real production frontend origin.
- Image tag is a deterministic (non-`latest`) value.
- ALB is locked to operator-only CIDRs as a compensating control for the lack of HTTPS.
- Terraform formatting and validation are both clean.

### 2. What is blocked only by the missing domain
- **HTTPS** (ACM certificate, HTTPS listener, HTTP→HTTPS redirect) — `module.dns`/`module.alb`'s HTTPS path is fully built and tested in source, wired to activate automatically the moment `domain_name` (and `create_dns_zone`/`existing_dns_zone_id`) are set to real values. No code change needed — only a tfvars value once a domain exists.
- **Widening `alb_ingress_cidrs` back to public (`0.0.0.0/0`)** — currently deliberately restricted; should stay restricted until HTTPS exists, then can open up.
- Everything else in this plan is **not** blocked by the domain — it's a genuinely separate concern from the rest of the stack.

### 3. What must change before public production (beyond the domain)
- **A real container image** built and pushed to the ECR repo this stack creates, under the tag actually referenced in `image_tag` (currently `sha-211daae` as a placeholder tag name, not a verified-existing image) — no GitHub Actions pipeline exists yet to automate this (architecture doc §9).
- **`alarm_email`** set to a real address — currently empty/pending.
- **LLM provider API keys** populated into the SSM parameters this stack creates (`aws ssm put-parameter`, per `infra/README.md`) — Terraform only creates placeholders.
- **(Recommended)** Move off root-user credentials to a scoped IAM role/user before running `apply`.
- **(Recommended)** Raise `api_min_capacity` to 2 for zero-downtime API task replacement, now that the RDS RunRegistry migration has landed in code.
- **(Recommended)** Migrate Terraform state to a remote (S3) backend before/shortly after first apply.

### 4. What can safely be tested using the ALB DNS name
Once applied, the ALB's own AWS-generated DNS name (`<name>.ap-south-1.elb.amazonaws.com`, plain HTTP, port 80) can be used for **controlled, operator-only validation** — reachable only from the two allow-listed CIDRs, not the public internet:
- End-to-end health check (`GET /health`), API task startup/replacement behavior, worker task pickup from SQS, RDS connectivity (the exact things staging's own verification report already exercised).
- **Not safe to test this way:** anything involving real user credentials/PII, since traffic is plaintext HTTP even from an allow-listed IP — use synthetic/throwaway test accounts only, exactly as staging's own report already did.

### 5. Current estimated cost drivers
See "Cost Findings" above for the ranked list; no changes to sizing/architecture were made this pass, so the estimate is unchanged from the architecture doc's own ~$85-160/month (low-traffic, on-demand pricing) figure. Worker Spot + scale-to-zero and single-NAT are the two cost optimizations already in place; RDS Single-AZ is the one deliberately-accepted availability/cost tradeoff.

## Deployment Risk

**Medium-Low**, improved from the first pass's "Medium": the plan is now fresh, verified, credentialed, and confirmed to include the security-group fix in actual plan output (not just source review) — the primary risk driver from the first pass is resolved. Remaining risk is entirely about **completeness for real use**, not correctness of what's configured: no HTTPS, no real image, no alarm notification target. None of these make an `apply` itself destructive or unsafe to the AWS account; they make the *result* not yet ready for public/real-user traffic.

## FINAL DECISION

**DO NOT APPLY**

This decision is held per explicit instruction, independent of the plan's own cleanliness (0 destroys, 0 replacements, security-group fix confirmed present, ALB locked down, CORS/image-tag resolved). Outstanding blockers: no production domain (HTTPS cannot be configured — by design, not invented), no alarm notification email yet, no real container image pushed to ECR, and no scoped (non-root) IAM credentials in use for the eventual apply. Terraform state remains local/unlocked.

**Path to APPROVED FOR APPLY:** provide a real production domain (or explicitly accept an interim HTTP-only, IP-restricted launch as a deliberate decision — not the current default), provide the alarm email, build and push a real image under an immutable tag and verify it exists in ECR, and switch to scoped IAM credentials for the apply itself. `terraform apply` is **not** run as part of this review regardless of outcome — that remains a separate, explicitly-triggered step.
