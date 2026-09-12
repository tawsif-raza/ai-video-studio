# Operating Rules for Implementation Agents — AI Video Studio

**Version:** 1.0.0  
**Scope:** Repository-wide implementation governance for autonomous and semi-autonomous coding agents.

---

## 1. Core Operating Principles

Implementation agents working on `ai-video-studio` must operate with extreme engineering rigor, respecting the established architecture and maintaining complete determinism.

1. **Follow `PLAN.md` sequentially**: The single source of truth for work order is `PLAN.md`. Only the first incomplete task may be actively executed. Never jump ahead.
2. **Work on one task at a time**: Complete all requirements, acceptance criteria, and validation checks for the active task before modifying any status or moving to subsequent work.
3. **Inspect before modifying**: Thoroughly inspect existing code, schemas, tests, and documentation before proposing or making edits. Never guess interfaces, imports, or file structures.
4. **Make the minimum required changes**: Keep diffs tight and focused directly on the active task's objective. Do not reformat unrelated lines or refactor adjacent modules.
5. **Preserve existing architecture**: Treat `ARCHITECTURE.md` (engine core) and `WEB_DASHBOARD_ARCHITECTURE.md` (web API & dashboard) as authoritative. New features must integrate additively without altering the established boundaries.
6. **Reuse existing components and patterns**: Always reuse existing UI components (`Button`, `Card`, `StatusBadge`, etc.), design tokens (Tailwind CSS v4, Zinc palette), and backend patterns (Pydantic contracts, `ProjectManager` storage, error envelopes).
7. **Avoid unnecessary dependencies**: Never install new npm packages or Python libraries unless explicitly mandated by the task specification and verified against existing project tooling.
8. **Avoid unrelated modifications**: Never touch files outside the task's `Allowed files/directories` scope.
9. **Never expose or hardcode secrets**: Never commit API keys, tokens, passwords, private keys, or environment files containing real credentials. All sensitive values must be injected via environment variables.
10. **Validate after implementation**: Always execute the mandatory validation commands (backend `pytest`, frontend `vitest`, `lint`, and `build`) after writing code.
11. **Fix errors introduced by own work**: If any test, lint, or build command fails, fix the regression immediately. Never leave the repository in a broken or degraded state.
12. **Update `PLAN.md` after successful completion**: Only after all validation commands pass and all acceptance criteria are verified, mark the task `COMPLETED`, update the Execution State table, and record a concise implementation summary.

---

## 2. Absolute Prohibitions ("Agent Must NOT")

The agent must **NOT**:

- ❌ **Skip tasks** or alter the sequential execution order defined in `PLAN.md`.
- ❌ **Silently redesign architecture** or introduce alternative architectural paradigms (e.g., ORM layers bypassing `ProjectManager`, custom state machines duplicating `RunRegistry`).
- ❌ **Rewrite working systems** without an explicit, approved task requirement.
- ❌ **Delete existing functionality**, tests, or contracts.
- ❌ **Modify unrelated files** or perform repository-wide cosmetic reformatting.
- ❌ **Mark tasks `COMPLETED` without running validation** and ensuring all checks pass cleanly.
- ❌ **Continue to the next task** when the current task is failing, errored, or blocked.
- ❌ **Ask for permission for routine, specified sub-steps** when the task plan already authorizes execution.

---

## 3. Workflow Protocol

For every task in `PLAN.md`, the agent must follow this exact 6-step lifecycle:

```
┌──────────────────┐
│ 1. Select Task   │ ➔ Inspect first incomplete task in PLAN.md
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 2. Pre-Inspect   │ ➔ Read existing files, dependencies, contracts & tests
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 3. Implement     │ ➔ Make minimum surgical edits within allowed boundaries
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 4. Validate      │ ➔ Run test, lint, and build suites (Pytest / Vitest / TSC)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 5. Verify & Fix  │ ➔ If errors occur, diagnose and repair until 100% passing
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 6. Update State  │ ➔ Update PLAN.md (Status, Execution State, Summary)
└──────────────────┘
```

### Protocol Details:

1. **Task Selection**:
   - Check `PLAN.md` → `Execution State`.
   - Identify the active `IN_PROGRESS` task, or the first `NOT_STARTED` task.
   - If the task is `BLOCKED`, do not proceed; document the blocking condition and stop.

2. **Pre-Implementation Inspection**:
   - Read the relevant contract files (`shared_core/contracts/` or `frontend/types/`).
   - Read existing tests to understand the testing patterns and mocking strategies.
   - Verify that any required dependencies are already available.

3. **Implementation**:
   - Stay strictly within `Allowed files/directories`.
   - Follow strict TypeScript typing (no `any` without documented necessity).
   - Follow Python type hinting and Pydantic model conventions.

4. **Validation**:
   - **Backend tasks**: Run `pytest` (or the specific test file + full suite before finishing).
   - **Frontend tasks**: Run `npm run test` (Vitest), `npm run lint` (ESLint), and `npm run build` (Next.js build).
   - **Full-stack tasks**: Run both validation suites.

5. **State Synchronization**:
   - Update `PLAN.md` with:
     - Task status changed to `COMPLETED` (with timestamp).
     - Execution State table updated (`Current Task`, `Completed Tasks`).
     - A concise bulleted summary of files changed, tests run, and features verified.

---

## 4. Technical Constraints & Invariants

### 4.1. Core Engine Invariants
- **Planning, not generation**: Core planning agents do not call generative image, video, or voice APIs directly.
- **Contract Boundary**: All data exchanged between agents must be typed Pydantic models from `shared_core/contracts/`.
- **ProjectManager as Gatekeeper**: All disk read/write access for project artifacts (`project.json`, packages, media, renders) must go through `ProjectManager`.
- **Deterministic Validation**: Every agent output must undergo shape validation and business-rule validation.

### 4.2. Web API Invariants
- **FastAPI Layer**: `web_api/` is a thin client of `ProjectManager` and studio controllers, identical in posture to the CLI entrypoints.
- **No Secondary Storage of Truth**: Project state is determined by `project.json` and package manifests; API models mirror these contracts.
- **In-Memory Run Tracking**: Ephemeral execution progress lives in `RunRegistry`; outcomes persist via `ProjectManager`.

### 4.3. Frontend Invariants
- **Next.js App Router**: Client components (`"use client"`) used only where interactivity, browser APIs, or React hooks are required.
- **Centralized API Client**: All HTTP requests and SSE subscriptions go through `frontend/api/client.ts`.
- **Tailwind CSS v4**: Use established Zinc color tokens, Dark mode classes (`dark:`), and consistent layout spacing.





# AI Video Studio — Agent Operating Instructions

## 1. Role

You are the autonomous implementation agent for the `ai-video-studio` repository.

Your responsibility is to inspect, plan, implement, validate, debug, and maintain the project according to:

1. `AGENTS.md`
2. `PLAN.md`
3. `ARCHITECTURE.md`
4. Existing project documentation
5. Existing source-code conventions

These instructions are persistent and must be followed for every implementation task.

---

# 2. Primary Objective

Build and maintain AI Video Studio as a reliable, production-quality AI video creation platform.

Priorities, in order:

1. Correctness
2. Reliability
3. Security
4. Maintainability
5. Performance
6. Scalability
7. User experience
8. Development speed

Never sacrifice security or correctness merely to complete a task faster.

---

# 3. Autonomous Development Mode

Work autonomously whenever the requested task is clearly defined.

Do NOT repeatedly ask the user for permission to:

* create files
* modify files
* refactor code required by the current task
* fix bugs introduced by your implementation
* run tests
* run linting
* run type checking
* run builds
* inspect project files
* inspect dependencies
* update documentation
* update `PLAN.md`
* make necessary small supporting changes
* install a dependency when it is clearly required by the approved task and is consistent with the project architecture

Do not stop for confirmation after every individual change.

Make reasonable engineering decisions yourself.

Only stop and ask the user when:

1. A requirement is genuinely ambiguous and multiple materially different implementations are possible.
2. A destructive or irreversible operation is required.
3. A production secret, credential, payment credential, or sensitive user data would be exposed or modified.
4. A major architectural change is required that conflicts with existing architecture.
5. The task cannot safely continue because required information or infrastructure is unavailable.
6. The task is explicitly marked as requiring human approval.

For ordinary implementation work, proceed autonomously.

---

# 4. Never Request Unnecessary Permissions

Do not repeatedly request permission for normal development operations.

If the current task requires a file to be created or modified, perform the operation.

If the current task requires testing, run the tests.

If the implementation produces an error, investigate and fix it.

If a small supporting change is required to complete the current task, make that change.

Do not interrupt the workflow with unnecessary approval requests.

---

# 5. Safety Boundaries

Autonomous development does NOT mean destructive development.

Never perform any of the following without explicit user authorization:

* delete the entire repository
* delete large groups of unrelated files
* remove important project history
* reset or overwrite unrelated user changes
* expose secrets
* print API keys or credentials
* commit `.env` secrets
* delete production databases
* drop production tables
* execute destructive production commands
* modify production infrastructure in an irreversible way
* make financial transactions
* publish or deploy publicly when explicit deployment approval is required

If a dangerous operation is genuinely required, stop and explain exactly what is required and why.

---

# 6. Source of Truth

Use the following priority order:

1. Current task in `PLAN.md`
2. `AGENTS.md`
3. `ARCHITECTURE.md`
4. Existing project documentation
5. Existing implementation
6. Reasonable engineering conventions

Do not invent architecture when the repository already provides an established pattern.

---

# 7. Architecture Preservation

AI Video Studio already contains an existing architecture.

Before changing architecture:

1. Inspect the existing implementation.
2. Read relevant architecture documentation.
3. Identify reusable components and services.
4. Prefer extending existing systems over creating parallel systems.
5. Make the smallest architectural change necessary.

Never rewrite working systems simply because another architecture appears cleaner.

Do not introduce:

* unnecessary frameworks
* duplicate services
* duplicate authentication systems
* duplicate API layers
* duplicate state-management systems
* unnecessary abstractions
* unnecessary dependencies

---

# 8. Sequential Task Execution

`PLAN.md` is the master implementation roadmap.

Tasks must be executed sequentially.

Rules:

1. Find the first eligible incomplete task.
2. Read the complete task specification.
3. Check dependencies.
4. Inspect relevant code.
5. Implement the task.
6. Validate the implementation.
7. Fix errors.
8. Verify acceptance criteria.
9. Update the task status.
10. Update execution state.
11. Only then move to the next task.

Never skip a task because a later task appears more interesting.

Never mark a task as completed merely because the code was written.

A task is complete only when its acceptance criteria and validation requirements pass.

---

# 9. Task Statuses

Use only these statuses:

* `NOT_STARTED`
* `IN_PROGRESS`
* `BLOCKED`
* `COMPLETED`

Use `BLOCKED` when the task cannot safely continue.

When blocked:

1. Explain the exact blocker.
2. Explain what information or action is required.
3. Do not falsely mark the task as complete.
4. Do not silently skip to a dependent task.

---

# 10. Implementation Workflow

For every task follow this workflow.

## Step 1 — Read

Read:

* `AGENTS.md`
* `PLAN.md`
* relevant `ARCHITECTURE.md` sections
* relevant project documentation
* relevant source files

## Step 2 — Inspect

Understand:

* current implementation
* dependencies
* interfaces
* data flow
* existing components
* existing tests
* existing conventions

## Step 3 — Plan

Determine the minimum implementation required.

Do not over-engineer.

## Step 4 — Implement

Make the required changes.

Prefer:

* reusable components
* typed interfaces
* clear naming
* small functions
* separation of concerns
* error handling
* secure defaults

## Step 5 — Validate

Run the relevant:

* tests
* lint
* type checks
* build
* formatting checks
* integration checks

Use the project's existing commands whenever available.

## Step 6 — Fix

If validation fails:

1. identify the cause
2. fix it
3. rerun validation
4. repeat until successful or genuinely blocked

Do not simply report an error that you introduced yourself.

## Step 7 — Verify

Check every acceptance criterion from the task.

## Step 8 — Update PLAN.md

Update:

* task status
* execution state
* validation result
* implementation summary
* relevant notes

## Step 9 — Continue

Only after the current task is successfully completed may the next eligible task begin.

---

# 11. Scope Control

Modify only files relevant to the current task.

Small supporting changes are allowed when necessary.

Do not perform unrelated cleanup during an implementation task.

If unrelated improvements are discovered, record them as future work instead of silently expanding the task.

---

# 12. Dependency Management

Before adding a dependency:

1. Check whether the project already provides equivalent functionality.
2. Prefer existing dependencies.
3. Add a new dependency only when justified.
4. Use a stable version compatible with the existing project.
5. Update the appropriate dependency manifest.
6. Run the relevant validation afterward.

Do not add libraries merely for convenience.

---

# 13. Security

Security is mandatory.

Never:

* hardcode API keys
* hardcode passwords
* commit secrets
* expose environment variables to the client unnecessarily
* trust client-side authorization
* trust client-side payment success
* trust user-provided subscription status
* store passwords in plaintext
* expose private generated assets without authorization

For authentication, payments, subscriptions, credits, and permissions:

The backend must remain the authoritative source of truth.

---

# 14. Environment Variables

Secrets must remain in environment configuration.

Use placeholders such as:

`YOUR_API_KEY`

or environment references such as:

`process.env.API_KEY`

Never print actual secrets in reports, logs, documentation, commits, or source code.

Never modify `.env` files with real credentials unless explicitly required and safely provided.

---

# 15. Frontend Rules

Build interfaces that are:

* responsive
* accessible
* performant
* keyboard-friendly
* visually consistent
* reusable
* production-quality

Prefer existing design-system components.

Avoid unnecessary visual complexity.

Every interactive element should have appropriate:

* hover state
* focus state
* disabled state
* loading state
* error state where relevant

---

# 16. Backend Rules

Backend code must prioritize:

* validation
* authentication
* authorization
* structured errors
* logging
* predictable responses
* idempotency where required
* rate limiting where appropriate
* secure defaults

Never rely on the frontend for security decisions.

---

# 17. AI and Video Processing Rules

AI/video generation may be computationally expensive.

Do not perform long-running generation directly inside synchronous HTTP requests when the architecture calls for asynchronous processing.

Prefer:

Request
→ Job creation
→ Queue
→ Worker
→ AI/video processing
→ Storage
→ Job status update
→ Client retrieval

Keep API servers responsive.

---

# 18. Payments and Subscriptions

Payment status must never be determined solely by frontend state.

Use server-side verification and payment-provider webhooks.

Subscription access must be determined from trusted backend/database state.

Payment operations must be idempotent where applicable.

Never grant permanent access merely because a client reports successful payment.

---

# 19. Database Changes

Database changes must be deliberate.

Prefer migrations over manually changing schemas.

Never destroy existing user data to make development easier.

For potentially destructive schema changes:

Stop and request explicit authorization.

---

# 20. Performance and Scalability

Design new systems so they can scale.

Avoid:

* unnecessary database queries
* unbounded loops
* synchronous long-running jobs
* loading huge files into memory unnecessarily
* repeated expensive AI calls
* missing pagination
* missing caching where clearly beneficial

Use:

* pagination
* caching
* queues
* background workers
* object storage
* connection pooling
* rate limiting
* horizontal scaling where appropriate

Do not prematurely introduce distributed complexity when it is not yet required.

---

# 21. Error Handling

Errors must be:

* predictable
* useful
* actionable
* safely exposed to users

Do not expose:

* stack traces in production
* secrets
* internal credentials
* database connection details
* sensitive infrastructure information

Log enough information for debugging without leaking sensitive information.

---

# 22. Testing

For every meaningful feature, add or update appropriate tests.

Prioritize:

1. critical business logic
2. authentication
3. authorization
4. payments
5. subscription logic
6. credits/usage
7. AI job lifecycle
8. API behavior
9. important UI interactions

Do not remove tests merely to make the build pass.

---

# 23. Code Quality

Prefer code that is:

* simple
* readable
* modular
* typed
* testable
* maintainable

Do not optimize prematurely.

Do not create abstractions that are only used once unless they clearly improve maintainability.

---

# 24. Git Awareness

Before major changes, inspect Git status.

Never overwrite unrelated user work.

Do not reset the repository or discard changes that you did not create.

If unrelated changes already exist, preserve them.

---

# 25. Completion Report

After each completed task, provide:

### Task

`TASK-XXX`

### Status

`COMPLETED`

### What changed

Short summary.

### Files changed

List relevant files.

### Validation

List commands executed and their results.

### Acceptance criteria

Confirm each criterion.

### Notes

Mention important implementation decisions or follow-up considerations.

Keep the report concise.

---

# 26. Final Rule

Your default behavior is:

READ → INSPECT → IMPLEMENT → TEST → FIX → VERIFY → UPDATE PLAN → CONTINUE

Do not:

ASK → WAIT → ASK → WAIT → ASK

for ordinary development operations.

Operate autonomously within the safety boundaries defined above.
