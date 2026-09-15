# AI Video Studio — AWS Production Architecture

**Status:** Planning only. No AWS resources were created or modified while writing this document. Nothing here should be provisioned until it's been reviewed and, where noted, until a named prerequisite (mainly: splitting the worker out, and moving off local disk) has landed in the codebase.

**Cost figures in this document are ballpark, us-east-1, on-demand pricing at time of writing** — verify against the AWS Pricing Calculator before committing budget; they exist to compare architectural options, not to be a quote.

---

## 0. What's actually in this repository today (verified, not assumed)

| Question | Answer | Evidence |
|---|---|---|
| Frontend framework | Next.js 16 (App Router, Turbopack), currently deployed on **Vercel** | `frontend/package.json`, `frontend/vercel.json`, CORS regex in `web_api/__init__.py` matching `*.vercel.app` |
| Backend framework | FastAPI on Uvicorn, single process | `ai_video_studio/api_app.py`, `web_api/create_app()` |
| API startup command | `uvicorn api_app:app --host 0.0.0.0 --port $PORT` | `railway.json`, `Dockerfile` |
| Worker/background execution | **In-process**, not a separate service: `BackgroundTasks` hands off to `PipelineExecutor` (`web_api/pipeline_executor.py`), a bounded `ThreadPoolExecutor` inside the *same* container as the API (`PIPELINE_MAX_CONCURRENCY=4` default, `PIPELINE_TIMEOUT_SECONDS=1800` default) | `web_api/pipeline_executor.py`, `docs/phase1.1-p0-fixes.md` |
| Docker configuration | `ai_video_studio/Dockerfile` (Python 3.11-slim base) for the backend; Railway actually builds via **Nixpacks** (`nixpacks.toml`), not this Dockerfile, to get `ffmpeg` onto `PATH` | `ai_video_studio/Dockerfile`, `nixpacks.toml`, `railway.json` |
| FFmpeg requirement | Real `ffmpeg`/`ffprobe` binaries, resolved via `shutil.which` on `PATH` — no bundled binary | `execution_engine/ffmpeg_detector.py`, `execution_engine/ffprobe_client.py` |
| CPU/RAM profile | Python side is I/O-bound (LLM HTTP calls) + light JSON/Pydantic work — **no** local ML/image/video libraries in `requirements.txt` (no torch, opencv, moviepy, numpy, PIL). The only CPU/RAM-intensive step is the `ffmpeg` subprocess itself, scaling with resolution/duration/codec | `requirements.txt` (pydantic, fastapi, uvicorn, httpx, google-genai, openai, requests, tenacity — nothing else) |
| Required ports | `8000` (or `$PORT`) for the API; frontend serves on `3000` in dev, static/edge in prod (Vercel) | `Dockerfile`, `railway.json` |
| Environment variables | LLM provider keys (`GEMINI_API_KEY`, `OPENAI_API_KEY`, `GROQ_API_KEY`, `CEREBRAS_API_KEY`, `OPENROUTER_API_KEY`), `AUTH_SECRET_KEY` (JWT signing), `DASHBOARD_CORS_ORIGINS`, `OUTPUT_DIR`, `PIPELINE_MAX_CONCURRENCY`, `PIPELINE_TIMEOUT_SECONDS`, `MIN/MAX_SCENE_COUNT`, model/tuning knobs — none are currently in a secrets manager, all read from `.env`/process env | `config.py`, `auth/security.py` |
| Database | **None.** All state is either in-memory (`RunRegistry`, lost on restart) or flat JSON files on local disk (`ProjectManager`, `LocalUserStore`) | `web_api/run_registry.py`, `auth/user_store.py`, `project_manager/manager.py` |
| Filesystem usage | Everything lives under `OUTPUT_DIR`: `projects/<id>/{production-package,producer-package,media,renders}/`, `users/<id>/user.json` — plain local disk, no S3/blob abstraction exists yet | `project_manager/manager.py`, `auth/user_store.py` |
| File upload behavior | Streamed straight to disk (`shutil.copyfileobj`) — already fixed for the memory-exhaustion risk found in the earlier stability audit; no size cap enforced server-side | `project_manager/manager.py::save_uploaded_media` |
| Generated-media storage | Rendered `.mp4` served back via `FileResponse` with HTTP Range support, straight off local disk (`GET /projects/{id}/render/video`) | `web_api/routers/render.py` |
| External APIs | 5 LLM providers with automatic failover (OpenRouter → Gemini → Groq → Cerebras → OpenAI, configurable order), optional YouTube publishing (degrades gracefully when unconfigured) | `llm/failover_client.py`, `publishing_engine/` |
| Health endpoints | `GET /health` (liveness-shaped, used as Railway's `healthcheckPath`), `GET /health/live`, `GET /health/ready` (checks `OUTPUT_DIR` writability) | `web_api/routers/system.py`, `web_api/routers/health.py` |
| Authentication | JWT (PyJWT, HS256), bearer header or HttpOnly cookie, PBKDF2-HMAC-SHA256 password hashing, file-backed user store | `auth/security.py`, `auth/user_store.py` |
| Current concurrency controls | `PipelineExecutor` bounds *in-process* concurrent pipeline runs (Phase 1.1 P0 fix); **no** infrastructure-level isolation between API traffic and heavy work — both share one container | `docs/phase1.1-p0-fixes.md` |
| Current job lifecycle | `RunRegistry`: `QUEUED → RUNNING → {SUCCEEDED, FAILED, TIMED_OUT, CANCELLED}`, **in-memory, single-process only** — this is the load-bearing constraint the rest of this document works around | `web_api/run_registry.py` |

**The one fact everything else in this document is built around:** `RunRegistry` is a plain Python dict in one process's memory. `DEPLOYMENT.md` already states this explicitly and enforces `numReplicas: 1` on Railway today. **This does not change** by moving to AWS — running more than one instance of the current API code, unmodified, silently breaks run-status lookups and SSE progress for any request that lands on a different instance than the one that started the run. Section 4/13 covers exactly what has to change to lift this.

---

## 1. Deployment Architecture

```
                                   Route 53 (api.yourdomain.com)
                                            │
                                            ▼
                                    ACM cert (HTTPS)
                                            │
                                            ▼
                              Application Load Balancer (public subnets)
                                    │ (+ optional WAF)
                                            │
                    ┌───────────────────────┴───────────────────────┐
                    ▼                                                ▼
         ECS Fargate: API service                         ECS Fargate: Worker service
         (private subnets, 1-N tasks)                      (private subnets, 0-N tasks)
         - FastAPI, HTTP + SSE only                         - Director/Producer/Render/
         - NO pipeline execution                              Publish pipeline execution
         - reads/writes RDS + S3                             - reads SQS, writes RDS + S3
                    │                                                │
                    └───────────────┬────────────────┬───────────────┘
                                     ▼                ▼
                              RDS PostgreSQL      Amazon SQS
                              (users, run/job      (job queue: director/
                               state)               producer/render/publish)
                                     │
                                     ▼
                              Amazon S3 (media uploads, production/
                              producer packages, rendered video)
                                     │
                                     ▼
                              CloudFront (serves rendered video
                              and any public media, optional at launch)

         Frontend: stays on Vercel (Next.js) — see §0/§11 for why.
         External: OpenRouter / Gemini / Groq / Cerebras / OpenAI / YouTube
         (only the Worker service needs a path to these, not the API service)
```

Two ECS services, one queue, one database, one bucket. Nothing else is load-bearing.

---

## 2. Network Architecture

- **One VPC**, 2 Availability Zones (minimum for anything called "high availability" — a single-AZ VPC is a single point of failure regardless of how many ECS tasks you run).
- **Public subnets** (2, one per AZ): ALB only.
- **Private subnets** (2, one per AZ): ECS tasks (API + worker), RDS.
- **NAT Gateway:** needed for the **worker service only** — it's the one that calls external LLM providers and YouTube. Put it in the calculation once, in one AZ, unless cross-AZ resilience for outbound calls specifically matters (it usually doesn't for retryable background jobs — a `FailoverLLMClient` already retries across providers). Two NAT Gateways (one per AZ) is the "textbook HA" answer; one NAT Gateway is the "reasonable cost" answer for a worker whose calls are already retried. **Recommendation: start with one NAT Gateway; add a second only if worker AZ-affinity becomes an actual observed problem.**
- **VPC Gateway Endpoint for S3** (free) and **Interface Endpoints for SQS/Secrets Manager/CloudWatch Logs** (~$7.30/month each): lets the **API service** reach S3/SQS/Secrets/CloudWatch **without any NAT Gateway at all**, since it never calls external LLM APIs directly once the worker split (§4) lands. This is a real, concrete cost reduction the split unlocks, not a nice-to-have.
- **Security groups:** ALB → API service (port 8000) only; API/worker services → RDS (5432) only; both services → VPC endpoints; worker → 0.0.0.0/0:443 via NAT only. No service accepts inbound from the internet except the ALB.

---

## 3. ECS Service Architecture

**API service** (`ai-video-studio-api`)
- Fargate, `awsvpc` networking, private subnets, registered as an ALB target group.
- Runs the **unmodified** FastAPI app minus the in-process pipeline dispatch (that becomes "enqueue to SQS" — see §4).
- `desiredCount`: starts at **2** once RunRegistry is externalized to RDS (§13); starts at **1** if you deploy before that migration (matches today's `numReplicas: 1` constraint exactly — do not raise this without doing the RDS work first, or you reproduce Railway's documented risk on AWS).
- Health check target: `GET /health` (already exists, already fast — confirmed in the Phase 1.1 stability work that this stays responsive under heavy load once pipeline execution is off the shared thread pool).
- `minimumHealthyPercent: 100`, `maximumPercent: 200` for zero-downtime rolling deploys.

**Worker service** (`ai-video-studio-worker`)
- Fargate (or Fargate Spot — see §12), private subnets, **no ALB, no inbound listener at all**.
- Polls SQS, runs exactly what `web_api/{director,producer,render,publish}_runner.py` already run today — same controllers, same `ProjectManager`, unmodified business logic.
- `desiredCount`: scales 0→N off queue depth (§13). Zero is a valid, cost-saving steady state when there's no work queued.
- No health check needed in the ALB sense; ECS's own container health check (process alive) plus CloudWatch alarms on queue age (§8) cover it.

Why two services and not one with two "modes": a single task definition that sometimes does light API work and sometimes does heavy ffmpeg work is exactly the coupling that caused the crash mechanism documented in `docs/phase1-stability-audit.md`. Two services means an OOM-killed worker task never touches the API's ability to answer `/health` or serve other users — that isolation is the whole point of this migration, not a detail.

---

## 4. Worker Architecture — the boundary, precisely

**Today:** `web_api/routers/projects.py`'s `create_project` (and the equivalent producer/render/publish routes) do:
```
background_tasks.add_task(pipeline_executor.submit, run_id=..., fn=run_director_pipeline, ...)
```
`pipeline_executor.submit` queues onto a `ThreadPoolExecutor` **inside the API container**.

**Target:** the route instead does:
```
sqs.send_message(QueueUrl=..., MessageBody=json.dumps({"stage": "director", "run_id": ..., "project_id": ..., ...}))
```
and returns the same `202 Accepted` it does today. The **worker service** runs a small poll loop:
```
while True:
    messages = sqs.receive_message(QueueUrl=..., WaitTimeSeconds=20, MaxNumberOfMessages=1)
    for msg in messages:
        dispatch to the existing run_director_pipeline/run_producer_pipeline/run_render_pipeline/run_publish_pipeline
        sqs.delete_message(...) only after it completes (success OR a handled failure - not on a crash)
```
`run_*_pipeline` functions themselves need **zero changes** — they already take exactly the arguments this dispatch loop has. `PipelineExecutor` itself (the bounded thread pool) can stay *inside the worker service* to bound how many jobs one worker task runs at once, or be dropped in favor of one job per SQS poll iteration plus ECS-level task scaling — either is reasonable; the thread pool version reuses more of the Phase 1.1 work.

**This is a real code change, not just infrastructure** — flagging that explicitly since this document's job was discovery/planning, not implementation. It should land as its own reviewed change before the AWS migration, matching what `PLAN.md`'s own `JOB-01` task already scopes ("Asynchronous Task Broker & Persistent Job Queue").

---

## 5. Database Architecture

**RDS PostgreSQL**, single small instance to start (`db.t4g.micro`, ~$12/month on-demand + storage), Multi-AZ **off** at launch (see §12 for why) with automated backups + point-in-time recovery on.

What moves into it:
1. **User accounts** (`LocalUserStore` → a `users` table). Filesystem-backed user storage doesn't survive multiple ECS tasks without a shared filesystem, and concurrent-write correctness on NFS-style storage is a worse bet than a real database designed for it.
2. **Run/job state** (`RunRegistry` → a `runs` table). This is what actually unlocks `desiredCount > 1` for the API service (§0's central constraint) — any API task can look up any run's status once it's a row in a shared database instead of a dict in one process's RAM.

What does **not** move into it: project content (production/producer packages, media, rendered video) — that's binary/blob data, it belongs in S3 (§6), not a relational database. Keep the database small and cheap; let S3 hold the bytes.

---

## 6. Storage Architecture

**S3**, one bucket (or one bucket with prefixes: `media/`, `production-package/`, `producer-package/`, `renders/`), replacing local-disk `OUTPUT_DIR`.

This requires the `StorageProvider` abstraction `PLAN.md`'s own `STOR-01` task already scopes — `ProjectManager` currently writes directly to `pathlib.Path`s everywhere; that needs an S3-backed implementation before this migration, not after. **Until that lands, do not deploy this app to ECS Fargate as-is** — Fargate tasks have no persistent local disk (ephemeral storage is wiped on every task replacement), so every project would be silently lost on the very first deploy or crash-restart, exactly as `DEPLOYMENT.md` already warns about for Railway, except guaranteed instead of "depends on scheduling."

**Two honest paths, pick one:**
- **A. Do the S3 migration first (recommended).** Real cloud-native storage, ~$0.023/GB-month, works naturally with CloudFront, no NFS mount to operate. Bigger code change.
- **B. Mount EFS at `OUTPUT_DIR`, ship unmodified.** Zero code changes — the app just sees a normal-looking directory. EFS is ~$0.30/GB-month (roughly **13x** S3's cost) plus a small per-AZ mount target charge, and every video byte round-trips through an NFS protocol instead of a direct S3 GET. Reasonable as a fast first step to get *something* running on AWS, not as the long-term answer given the stated cost-consciousness.

**Recommendation: A for the actual production launch, B only if you need something running on AWS before the storage code change is ready and are willing to migrate off it shortly after.**

Rendered video is served today via `FileResponse` with Range support straight from the API process — with S3, that becomes either (a) the API/worker generates a pre-signed S3 URL and the browser downloads directly from S3/CloudFront (recommended: takes the byte-serving entirely off your compute layer), or (b) the API proxies the S3 object through (keeps the existing "never leak a filesystem path" contract exactly, at the cost of routing bytes through ECS). (a) is cheaper and simpler; (b) matches the current code's documented intent most literally. Worth a deliberate choice when the S3 migration is designed, not decided here.

---

## 7. Queue Architecture

**One SQS standard queue** (`ai-video-studio-jobs`), one **dead-letter queue** (`ai-video-studio-jobs-dlq`) with `maxReceiveCount: 3`.

- **Why standard, not FIFO:** nothing about Director/Producer/Render/Publish jobs requires strict ordering across different projects, and standard queues are cheaper and higher-throughput. Per-project ordering isn't needed either — `RunRegistry`'s existing one-active-run-per-project rule already prevents a project from having two runs in flight at once; the queue doesn't need to re-enforce that.
- **Visibility timeout:** set comfortably above `PIPELINE_TIMEOUT_SECONDS` (1800s today) — e.g. 2100s — so SQS doesn't redeliver a message while a worker is still legitimately processing it.
- **DLQ:** after 3 failed processing attempts, a message lands here instead of looping forever — directly addresses the "unbounded retries" resource-risk category from the original stability audit, and gives an operator a concrete place to look when a job is stuck rather than a growing, silently-retried backlog.
- One queue, four message "stage" types (`director`/`producer`/`render`/`publish`), dispatched by the worker's own existing per-stage functions — no need for four separate queues unless render/publish traffic patterns diverge enough to want independent scaling later (§13 covers that).

---

## 8. Monitoring Architecture

- **CloudWatch Logs:** both ECS services log to stdout/stderr (already true today — `utils/logger.py`), captured automatically by the `awslogs` driver. Set retention to **30-90 days**, not indefinite — unbounded log retention is a real, boring, easy-to-miss cost leak.
- **CloudWatch Alarms** (the ones that actually matter for this app specifically, not a generic checklist):
  - ALB target `UnHealthyHostCount > 0` for 2+ minutes → paging alert (the exact signal that would have caught the original thread-pool-starvation crash mode before a user did).
  - SQS `ApproximateAgeOfOldestMessage` above a threshold (e.g. 10 minutes) → the queue-backlog early-warning signal, also drives worker auto-scaling (§13).
  - SQS `ApproximateNumberOfMessagesVisible` on the DLQ > 0 → something is failing repeatedly; page, don't silently drop.
  - RDS `FreeStorageSpace` and `CPUUtilization` — standard, cheap insurance.
  - ECS service `CPUUtilization`/`MemoryUtilization` per service — the concrete data needed to right-size §11's sizing guesses after real traffic.
- **CloudWatch Dashboards:** one dashboard per service is enough at this scale; don't build a bespoke observability stack for a two-service app.
- Explicitly **not recommended yet**: OpenSearch/ELK for log search, X-Ray distributed tracing, or a third-party APM. Two services and one queue don't need distributed tracing to debug; CloudWatch Logs Insights queries are sufficient until the architecture actually grows more services.

---

## 9. Deployment Pipeline

- **Source → build:** GitHub Actions (the repo already lives on GitHub; no CI exists yet — confirmed, no `.github/workflows` present). Build the API and worker Docker images (likely the same image with a different container `command`, since they share the same codebase — see below), push to **ECR**.
- **Auth to AWS:** GitHub's OIDC provider → a scoped IAM role (`ecr:PutImage`, `ecs:UpdateService` on the two specific services) — **no long-lived AWS access keys stored in GitHub secrets.**
- **Deploy:** `aws ecs update-service --force-new-deployment` (or the `amazon-ecs-deploy-task-definition` GitHub Action) for both services. ECS's native rolling deployment (`minimumHealthyPercent`/`maximumPercent`) with the ALB health check gating the API service is sufficient — CodeDeploy blue/green is a reasonable upgrade later if you want automated rollback on elevated 5xx rate specifically, not a launch requirement.
- **One image, two commands:** the API and worker are the same codebase (`ai_video_studio/`) with different entrypoints (`uvicorn api_app:app ...` vs. the SQS poll loop from §4) — build **one** image, reference it from **two** ECS task definitions with different `command` overrides. Simpler pipeline, one thing to build and scan, no drift between "API's copy of the code" and "worker's copy of the code."
- **Rollback:** ECS task definitions are versioned automatically; rolling back is `update-service` pointed at the previous task definition revision. Keep the last 5-10 revisions (default retention is fine).

---

## 10. Security Model

- **Secrets:** RDS credentials in **Secrets Manager** (native RDS integration, supports rotation, ~$0.40/secret/month). LLM API keys and the JWT signing secret (`AUTH_SECRET_KEY`) in **SSM Parameter Store (SecureString)** instead — functionally equivalent for "don't put it in an env var in plaintext," and free for standard parameters, which this app's key count comfortably fits under. Using Secrets Manager for everything is defensible too; the split above is the cost-optimized version of the same security posture.
- **IAM:** two ECS task roles, least-privilege — API task role gets S3 read/write on its prefixes + SQS `SendMessage` + RDS connect; worker task role gets S3 read/write + SQS `ReceiveMessage`/`DeleteMessage`/`ChangeMessageVisibility` + RDS connect. Neither needs the other's queue permissions in the opposite direction.
- **WAF on the ALB:** AWS Managed Common Rule Set + a rate-based rule specifically on `/auth/login` and `/auth/register`. This directly closes the gap `PLAN.md`'s own `INFRA-02` task already flags as `NOT_STARTED` (no rate limiting exists in the app today) — cheaper and faster to get here via WAF than writing app-level rate-limiting middleware first. ~$5/month base + ~$1/rule + $0.60/million requests.
- **TLS:** ACM certificate on the ALB (and CloudFront, if used) — free, auto-renewing.
- **Authentication:** the app's existing JWT/cookie model is unchanged by this migration; only its *user store* moves (file → RDS row, §5). Nothing about the auth design itself needs to change for AWS.
- **Network:** private subnets for everything except the ALB (§2) — no ECS task, and no RDS instance, is ever directly internet-reachable.

---

## 11. Estimated Resource Sizing (starting point — tune from real CloudWatch data, not this table)

| Resource | Starting size | Monthly cost (on-demand, ballpark) |
|---|---|---|
| API service (Fargate) | 0.5 vCPU / 1 GB, 1-2 tasks | ~$15-30 |
| Worker service (Fargate, on-demand baseline) | 1 vCPU / 2 GB, 0-2 tasks (scales with queue) | ~$0-60 depending on load |
| RDS `db.t4g.micro` | Single-AZ, 20GB gp3 | ~$15 |
| NAT Gateway | 1 | ~$33 + data processing |
| ALB | 1 | ~$16 + LCU usage |
| S3 | Pay-per-GB, pay-per-request | ~$0.023/GB-month + request costs — genuinely cheap at this app's scale |
| SQS | Pay-per-request | Effectively $0-2/month at low-to-moderate volume (first 1M requests/month free) |
| CloudWatch Logs | 30-day retention | ~$5-15 depending on log volume |
| Secrets Manager (1-2 secrets) | | ~$1 |
| **Rough total, low traffic** | | **~$85-160/month**, dominated by NAT Gateway + ALB, both fixed costs regardless of traffic |

The Fargate figures above assume Python/ffmpeg CPU/RAM needs similar to what's already observed on Railway — **not independently re-measured here**; the original stability audit already flagged that real CPU/RAM under load was never measured (no `ffmpeg` available in that environment). Measure real utilization for a week after launch before trusting these numbers for capacity planning.

---

## 12. Cost-Control Strategy

1. **Worker service scales to zero** when the queue is empty (§13) — you don't pay for idle ffmpeg capacity between jobs, unlike a single always-on container doing everything.
2. **Fargate Spot for the worker service.** Video generation jobs are already designed to be retryable (idempotent render output, SQS redelivery on failure) — a Spot interruption just means the message becomes visible again and another task picks it up. Spot is ~70% cheaper than on-demand Fargate. **Do not** put the API service on Spot — user-facing request handling shouldn't be interrupted for a cost saving that small in absolute dollars.
3. **RDS Single-AZ, not Multi-AZ, at launch.** Multi-AZ roughly doubles RDS cost for automatic failover this app's user base likely doesn't need on day one; automated backups + PITR already protect against data loss, just not against an availability gap during an AZ failure. Upgrade to Multi-AZ once real usage justifies it, not preemptively.
4. **One NAT Gateway, not two** (§2) — the worker's external calls already retry across 5 LLM providers; AZ-level NAT redundancy is a smaller marginal reliability gain than its ~$33/month duplicate cost, for this specific workload.
5. **S3 over EFS** (§6) — the ~13x per-GB cost difference compounds directly with however much rendered video this app accumulates.
6. **CloudWatch log retention capped**, not indefinite (§8).
7. **SSM Parameter Store over Secrets Manager** for the secrets that don't need rotation (§10) — free vs. $0.40/secret/month is trivial per-secret, but it's the right default to reach for.
8. **Skip CloudFront at launch** unless rendered-video egress volume is already large enough to matter, or global latency to end users is a known requirement — it's a genuine win once video-serving traffic is real, not before there's traffic to optimize.

---

## 13. Scaling Strategy

- **API service:** ECS Service Auto Scaling on ALB `RequestCountPerTarget` (or CPU, either is reasonable for a mostly-I/O-bound FastAPI app) — standard target-tracking, min 1-2 / max whatever traffic actually demands. **This only becomes meaningful (more than 1 task) once RunRegistry moves to RDS (§5)** — scaling the API service before that migration reproduces the exact bug `DEPLOYMENT.md` already documents on Railway.
- **Worker service:** ECS Service Auto Scaling on the SQS `ApproximateNumberOfMessagesVisible` metric (a standard CloudWatch-alarm-driven step-scaling policy) — scale out as the backlog grows, back to 0 when it's empty. This is the AWS-native version of exactly the "bounded, queued, doesn't let one heavy user starve everyone else" property `PipelineExecutor` (Phase 1.1) already built at the application level — the queue gives you the same property at the infrastructure level, with the added benefit of being able to add worker capacity instead of just queuing longer.
- **Database:** vertical scaling (bigger instance class) is the right first move for RDS if it becomes a bottleneck — this app's DB load (user rows + run-state rows) is small and simple; don't reach for read replicas or Aurora until there's a measured reason to.
- **Storage:** S3 scales without any action from you.

---

## 14. Failure Scenarios

| Scenario | What happens | Why it's handled |
|---|---|---|
| A worker task OOMs mid-render | ECS replaces the task; the in-flight SQS message becomes visible again after the visibility timeout and another task picks it up | Isolated from the API service entirely — this is the core reliability win of the split in §3/§4 |
| A worker job fails 3 times (bad input, persistent bug) | Lands in the DLQ instead of looping forever | §7 — directly closes the "unbounded retries" resource risk from the original stability audit |
| An API task crashes | ALB marks it unhealthy, ECS replaces it; other tasks (once `desiredCount > 1` is safe, §5/§13) keep serving | Standard ECS self-healing; no in-flight pipeline work is lost since it lives in SQS/RDS, not that task's memory |
| One AZ goes down | ALB, ECS tasks, and RDS (if Multi-AZ is later enabled) are already spread across 2 AZs | §2's baseline network design |
| An LLM provider has an outage | `FailoverLLMClient` already retries across 5 configured providers before failing a job | Existing app-level resilience, unaffected by this migration |
| The SQS queue backs up (LLM providers slow, or a demand spike) | `ApproximateAgeOfOldestMessage` alarm fires, worker service scales out (up to its max); if it's still not enough, the alarm pages a human | §8 + §13 |
| A bad deploy breaks the API | ECS rolling deployment with health-check gating stops promoting new tasks that fail `/health`; roll back to the previous task definition revision | §9 |
| RDS becomes unavailable (Single-AZ, launch config) | Automated backups + PITR limit data loss; there is a real availability gap until it's replaced — this is the one deliberately-accepted risk in §12's cost-control strategy, revisit if/when it's no longer acceptable | §5/§12, stated explicitly rather than hidden |

---

## Critical Question — Answered

**Can the current application safely run heavy video generation inside the API container?**

**For a single, cost-conscious deployment at modest scale: yes, provisionally.** The Phase 1.1 P0 fix (`PipelineExecutor`, `docs/phase1.1-p0-fixes.md`) already solved the specific crash mechanism found in the stability audit — heavy pipeline work no longer shares the same thread pool as `/health` and ordinary API traffic, and it's bounded (`PIPELINE_MAX_CONCURRENCY`) and time-limited (`PIPELINE_TIMEOUT_SECONDS`), verified by the reproduction in that document (health latency stayed at ~1-7ms under a 45-request burst).

**For genuine AWS production reliability — the objectives this document was asked to satisfy (heavy workload isolation, automatic recovery, controlled scaling) — no, not as-is.** The remaining problem isn't thread-pool starvation anymore; it's that the API and the heavy work still share one **container**, one CPU/memory allocation, and one failure domain. An OOM'd ffmpeg process still takes the whole task down — API traffic included — because it's the same process's memory space. There's no way to scale "video rendering capacity" independently of "API request capacity" when they're the same ECS service. And Fargate's ephemeral storage means the current local-disk model can't survive a task replacement at all, regardless of the concurrency fix.

**Exactly where the worker boundary should be:** between the HTTP route handler and pipeline execution — precisely the seam `PipelineExecutor.submit()` already sits at today. §4 describes the specific, minimal change: replace that one call with an SQS `send_message`, and run the *unmodified* `run_director_pipeline`/`run_producer_pipeline`/`run_render_pipeline`/`run_publish_pipeline` functions in a separate ECS service that polls the queue. Everything downstream of that line — the controllers, the agents, `ffmpeg_executor.py` — needs no changes at all.

---

## What has to happen before any of this is provisioned

In order, because each depends on the last:
1. **S3-backed storage** (`StorageProvider` abstraction, `PLAN.md`'s `STOR-01`) — Fargate has no persistent local disk; without this, step 3 below loses every project on the first task replacement.
2. **RDS-backed `RunRegistry` and user store** — required before the API service can safely run more than one task, and before the worker split (step 3) has anywhere durable to record job outcomes.
3. **The worker split itself** (§4) — SQS producer in the API routes, SQS consumer in a new worker service entrypoint, using the existing runner functions unmodified.
4. **Then** the AWS infrastructure in this document, ideally as Terraform or CDK rather than console clicks, so it's reproducible and reviewable the same way the application code already is.

Everything in this document is designed to make that sequence as small as possible — reusing the app's existing runner functions, controllers, and Phase 1.1 concurrency work unmodified, and introducing exactly three new pieces of infrastructure (S3, RDS, SQS) rather than a larger platform rebuild.
