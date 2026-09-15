# AI Video Studio — Staging Deployment Verification Report

**Date:** 2026-09-13/14
**Environment:** `infra/environments/staging` (AWS `ap-south-1`, account `801702847930`)
**Cluster:** `ai-video-studio-staging`

## 1. Summary

The staging environment is deployed and verified end-to-end: API service, worker
service, RDS PostgreSQL, S3, SQS, and the full Director Studio AI pipeline all
work together correctly, including under induced failure conditions. Two real
bugs were found and fixed during verification (not staged/simulated — both were
hit organically while testing the actual deployment). The environment is **not
yet publicly exposed** (ALB ingress is restricted to specific operator IPs) and
Fargate Spot is disabled for the worker, per the original constraints ("prove
correctness first").

## 2. Bugs found and fixed during this verification pass

### 2.1 API/worker had no network path to RDS at all (P0 — blocked all DB access)

**Symptom:** API container crashed on every startup with
`psycopg_pool.PoolTimeout: couldn't get a connection after 30.00 sec` during
`init_schema()`.

**Root cause:** `infra/modules/security_groups/main.tf` mixed inline
`egress` blocks on `aws_security_group.api`/`.worker` with separate
`aws_security_group_rule.api_to_rds`/`worker_to_rds` resources targeting the
*same* security groups. This is an explicit AWS-provider conflict: a security
group with any inline ingress/egress blocks treats those blocks as the
complete authoritative rule set for that direction on every apply, so the
separately-managed RDS egress rules were silently revoked. Confirmed live: the
API security group had only 2 egress rules (VPC endpoints, internet) — no rule
to RDS at all, on either the API or worker security group.

**Fix:** Refactored `infra/modules/security_groups/main.tf` so `aws_security_group.api`
and `.worker` carry **no** inline egress blocks — every egress rule (VPC
endpoints, RDS, internet) is now a standalone `aws_security_group_rule`. Used
`terraform import` to reconcile the pre-existing live rules into the new
resource addresses instead of destroying/recreating them.

**Note:** An unrelated, real latent bug was also fixed opportunistically —
`db/connection.py` built its libpq conninfo via naive f-string interpolation,
which would silently corrupt a master password containing a space or other
libpq-significant character. Replaced with `psycopg.conninfo.make_conninfo()`.
This was *not* the cause of the outage (the SG fix alone resolved it), but is
a correct hardening fix.

### 2.2 Cross-task S3 cache staleness (real bug, not a simulated scenario)

**Symptom:** After a worker task completed a full Director Studio run and
wrote `PACKAGE_READY` status + all pipeline artifacts to S3, the API kept
returning the project stuck at status `CREATED` with every `source_*_id`
field null — indefinitely, not just briefly.

**Root cause:** `storage/s3_project_sync.py`'s `ensure_local()` only checked
"do I have *a* local copy of project.json" before deciding whether to pull
from S3. An API task that had merely *created* the project (and so already
had a local copy from that point in time) would never sync down again for
that project's entire lifetime — even after a different task (the worker, on
its own ephemeral disk) updated S3 with the real results. This directly
defeated the reason `S3ProjectSync` exists (§5 of the architecture doc:
correctness once more than one task can touch a project).

**Fix:** `ensure_local()` now compares S3's current `ETag` for `project.json`
against the ETag this task last synced (stored in a local sidecar file kept
outside the synced directory tree so it's never itself uploaded to S3), and
only skips the download when they match. Added a regression test
(`test_ensure_local_redownloads_when_s3_has_a_newer_version`) and updated the
existing "no-op when cached" test to correctly assert staleness-aware
behavior rather than "cached forever." All 17 `tests/storage/` tests pass.

**Status:** Fixed, deployed (image tag `staging-wip-202609132309`), and
verified live — `GET /projects/{id}` now correctly returns `PACKAGE_READY`
with all source IDs populated after a worker-completed run.

Both fixes are currently **uncommitted** in the working tree (along with the
rest of the AWS-deployment prerequisite work from this engagement) — commit
on request.

## 3. Verification results

| Check | Result |
|---|---|
| API task starts, health check passes | ✅ Pass |
| ALB reaches the application | ✅ Pass (`GET /health` → `200`) |
| Database connectivity | ✅ Pass (after §2.1 fix) |
| Authentication end-to-end via ALB | ✅ Pass (register 201, login 200) |
| S3 access (project write) | ✅ Pass (`project.json` appears in bucket) |
| Secrets loading (JWT key, LLM keys) | ✅ Pass |
| Logs (CloudWatch) | ✅ Pass — clean startup sequence visible |
| Worker deployment | ✅ Pass — scales 0→N on SQS backlog, N→0 when idle |
| Full pipeline: API→SQS→Worker→LLM→S3→DB | ✅ Pass — real Director Studio run completed to `PACKAGE_READY` with real LLM keys |
| Kill API task | ✅ Pass — ECS replaced it automatically; ~20s ALB outage window (inherent to `api_min_capacity=1`, see §5) |
| Kill worker task | ✅ Pass — API stayed at `200` throughout; worker lifecycle managed correctly by autoscaling |
| Stop database temporarily | ✅ Pass — `/health` stayed `200` throughout (no crash/restart-loop); DB-dependent calls failed with a clean, logged connection error (generic `500`, not a distinguished `503` — minor, see §5); auto-reconnected with zero intervention once RDS came back |
| Submit multiple/concurrent jobs | ✅ Infra pass / ⚠️ found real external limit — worker autoscaled 0→2 correctly and picked up all 3 messages with proper in-flight tracking, but all 3 runs failed on OpenRouter `402` ("exceeds available credits given current in-flight requests") on the real account. This is a constraint on the OpenRouter account, not an infrastructure defect — failure handling itself worked correctly (clean failure per run, no crash, worker kept polling). |
| Upload a large file | ✅ Pass — 3MB multipart upload succeeded (201, correct path/size). A 25MB upload did not complete within the test session's ~57 KB/s outbound bandwidth (this sandbox's own network, not AWS) — mechanism is verified; true large-file throughput should be re-tested from a normal network. |
| Heavy generation (full image/video render) | ⏭ Not run — skipped per your decision, given the OpenRouter constraint above; the Director Studio text/planning pipeline (research→story→scene→shot→camera→character→environment→prompt→voice script→production package) was run for real and verified end-to-end twice. |

## 4. Current resource configuration (as deployed, staging)

| Resource | Configuration |
|---|---|
| RDS | `db.t4g.micro`, PostgreSQL 16.13, 20 GB storage, Single-AZ |
| ECS API task | 512 CPU / 1024 MiB, Fargate (not Spot), desired 1, autoscaling 1–4 |
| ECS worker task | 1024 CPU / 2048 MiB, Fargate (Spot disabled per your instruction), autoscaling 0–10, scales on SQS backlog |
| ALB ingress | Restricted to specific operator CIDRs (not `0.0.0.0/0`) — **not publicly exposed** |
| NAT | Single NAT Gateway |
| VPC endpoints | s3 (gateway), sqs, secretsmanager, ssm, logs, ecr.api, ecr.dkr (interface) |
| API egress escape hatch | `api_allow_internet_egress = true` — temporary, see known follow-up below |

## 5. Known follow-ups (not blocking, documented for later)

- **`api_min_capacity = 1`**: killing the sole API task causes a real ~20s
  ALB outage window before the replacement becomes healthy. Raise to ≥2 for
  true zero-downtime failover in production.
- **DB-unavailable errors surface as generic `500`s**, not a distinguished
  `503 Service Unavailable`. Not a crash risk (the process itself never
  crashed/restart-looped during the RDS-stop test), but a `503` would let
  clients/monitoring distinguish "our bug" from "a downstream dependency is
  down."
- **`api_allow_internet_egress = true`** is a temporary escape hatch (see
  `infra/environments/staging/variables.tf`'s own description) — a
  `ecr.api`/`ecr.dkr` VPC-endpoint image-layer-pull timeout wasn't fully
  root-caused during initial provisioning. Worth revisiting before this
  posture is copied into production.
- **Large-file upload throughput** was only exercised at 3MB from a
  bandwidth-constrained test environment; worth a real-network re-test before
  relying on this number for production capacity planning.
- **OpenRouter account concurrency/credit ceiling**: 3 simultaneous pipeline
  runs exhausted the account's in-flight request allowance. Not an
  infrastructure issue, but worth knowing before enabling real concurrent
  usage at scale.
