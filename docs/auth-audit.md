# Authentication Audit

Audit performed before any implementation work, per the task's Phase 1 requirement. Findings below reflect the state of the repository as of 2026-09-17, before the fixes described in the "Root Cause" / "Required Changes" sections were applied.

## Frontend Auth Architecture

- `frontend/features/auth/AuthContext.tsx` — React context (`AuthProvider`/`useAuth`) holding `user`, `token`, `isAuthenticated`, `isLoading`. On mount it reads a JWT from `localStorage` (`api/token-storage.ts`, key `studio_access_token`) and calls `GET /auth/me` to hydrate `user`. `login`/`signup`/`logout` call the backend and update local state + storage.
- `frontend/features/auth/ProtectedRoute.tsx` — wraps the whole app (`app/layout.tsx`), redirects unauthenticated users to `/login?next=...` and authenticated users away from `/login`/`/signup`, and blocks content flashing while `isLoading`.
- `frontend/features/auth/{LoginForm,SignupForm,ForgotPasswordForm,ResetPasswordForm}.tsx` — fully built forms with client-side validation, loading/error/success states, show/hide password, and a clearly-labeled Google Sign-In *placeholder* button (not wired to real OAuth).
- `frontend/api/auth.ts` — direct `fetch()` calls (not routed through `api/client.ts`) for `login/register/getMe/logout/forgot-password/reset-password`, each sending `credentials: "include"` and, where relevant, an `Authorization: Bearer <token>` header sourced from `localStorage`.
- `frontend/api/client.ts` — the shared request layer (`apiGet/apiPost/apiDelete/apiPostForm/apiPostFormWithProgress`) used by `api/projects.ts`, `api/packages.ts`, `api/runs.ts` for all actual project/producer/render/publish/run data. **This layer did not attach any authentication at all** (see Root Cause).

## Backend Auth Architecture

- `ai_video_studio/auth/security.py` — PBKDF2-HMAC-SHA256 password hashing (100k iterations, per-user random salt), JWT access tokens (HS256, 24h expiry) and single-purpose JWT password-reset tokens (1h expiry, `scope: password_reset`, bound to a fingerprint of the current password hash so they invalidate on use).
- `ai_video_studio/auth/user_store.py` — `UserStore` ABC + `LocalUserStore` (filesystem JSON under `OUTPUT_DIR/users/<id>/user.json`, used whenever `DB_HOST` is unset — i.e. local dev and the entire test suite).
- `ai_video_studio/db/postgres_user_store.py` — Postgres-backed `UserStore` implementation, selected automatically by `web_api/dependencies.py:get_user_store` when `DB_HOST` is configured (staging/production).
- `ai_video_studio/web_api/routers/auth.py` — `/auth/register`, `/auth/login`, `/auth/me` (GET/PATCH), `/auth/me/password`, `/auth/logout`, `/auth/forgot-password`, `/auth/reset-password`. Mounted twice in `web_api/__init__.py` (once bare, once under `/api`), so both `/auth/...` and `/api/auth/...` work.
- `ai_video_studio/web_api/dependencies.py:get_current_user` / `get_optional_current_user` — extract a JWT from `Authorization: Bearer ...`, the `access_token` cookie, or the `session_token` cookie (checked in that order); decode/validate it; load the user; strip `hashed_password`/`salt` before returning.
- `ai_video_studio/shared_core/contracts/user.py` — Pydantic models (`UserCreate`, `User`, `UserInDB`, `UserResponse`, etc.). `UserInDB` never serializes to `UserResponse` with the hash/salt included.

## Existing Endpoints

| Method | Path | Auth |
|---|---|---|
| POST | `/auth/register` | public |
| POST | `/auth/login` | public |
| GET | `/auth/me` | required (`get_current_user`) |
| PATCH | `/auth/me` | required |
| PATCH | `/auth/me/password` | required |
| POST | `/auth/logout` | public (clears cookies if present) |
| POST | `/auth/forgot-password` | public, neutral response (no enumeration) |
| POST | `/auth/reset-password` | public, single-use token |
| POST/GET/DELETE | `/projects*` | optional (`get_optional_current_user`) + ownership check |
| POST/GET | `/projects/{id}/producer/*`, `/render/*`, `/publish/*` | **none at audit time** (see Root Cause) |
| GET | `/runs/{run_id}` | **none at audit time** |
| GET | `/runs/{run_id}/events`, `/projects/{id}/events` | **none at audit time** |

All of these endpoints are already covered by `app.include_router(...)` in `web_api/__init__.py`; nothing needed to be newly wired up.

## Session Mechanism

Dual-mode by design: the backend issues both (a) a JSON `access_token` in the response body and (b) an `HttpOnly` cookie of the same JWT. The frontend's actual source of truth is (a) — the token is kept in `localStorage` and sent as `Authorization: Bearer <token>` — not the cookie. The cookie exists as a defense-in-depth fallback that `get_current_user` will also accept, but nothing in the shipped frontend code relied on it exclusively.

## Cookie Configuration

`response.set_cookie(key="access_token", httponly=True, samesite="lax", secure=False, max_age=86400, path="/")` (`web_api/routers/auth.py`). `secure=False` is correct for local HTTP dev; it must become `True` behind HTTPS in staging/production (see Required Changes / Production Configuration below — currently **not environment-conditional**, flagged as a finding).

## Password Hashing

PBKDF2-HMAC-SHA256, 100,000 iterations, random 16-byte salt per user, constant-time comparison (`hmac.compare_digest`) on verify. No plaintext or reversibly-encrypted password is ever stored. This is solid; no change made.

## User Database Model

`UserInDB`: `id` (UUID4 str), `email`, `full_name`, `is_active`, `preferences`, `api_keys`, `hashed_password`, `salt`, `created_at`, `updated_at`. Matches the task's minimum-field requirement. Local dev stores this as JSON per user; production uses Postgres (`db/postgres_user_store.py`, schema in `db/connection.py`).

## CORS Configuration

`web_api/__init__.py:_cors_origins()` — defaults to `["http://localhost:3000", "http://127.0.0.1:3000"]`, overridable via `DASHBOARD_CORS_ORIGINS` (comma-separated), plus a regex allowing any `ai-video-studio-dashboard*.vercel.app` preview/production URL. `allow_credentials=True` with a non-wildcard origin list, which is required for cookie/credentialed `fetch()` to work at all cross-origin. This is correctly implemented already. One local-environment note: this machine had something else already bound to port 3000, so `next dev` fell back to port 3001, which is *not* in the default origin list — verification required temporarily setting `DASHBOARD_CORS_ORIGINS` to include `http://localhost:3001`. Not a code defect (the default matches Next.js's standard dev port); noted here only so it isn't mistaken for one.

## Protected Routes

Frontend: `ProtectedRoute` (see above) correctly gates every route except `/login`, `/signup`, `/forgot-password`, `/reset-password`, redirecting based on `GET /auth/me`'s result, not a locally-assumed flag. Verified live in a real browser (Phase 19) that a direct navigation to a protected route while logged out redirects to `/login?next=<path>`, and that after logout the app does not remain accessible via back navigation, because `ProtectedRoute` re-evaluates `isAuthenticated` from `AuthContext` state (cleared on logout) rather than from any bfcache-restored DOM.

Backend: `/projects*` enforced ownership already (see below). `/projects/{id}/producer|render|publish/*`, `/runs/{run_id}`, and both SSE event endpoints did **not** — see Root Cause.

## Current Login Failure

There was no failure in the login mechanism itself — `POST /auth/login`, `GET /auth/me`, and the frontend `AuthContext`/`LoginForm` all worked correctly in isolation and were covered by 37 existing backend tests (`tests/web_api/test_auth.py`) and 6 existing frontend test files. The user-visible symptom ("authentication is not fully working end-to-end") traces to what happens *after* login: the rest of the application's data layer silently ignored the logged-in session.

## Root Cause

`frontend/api/client.ts` (the shared `apiGet`/`apiPost`/`apiDelete`/`apiPostForm`/`apiPostFormWithProgress` helpers used by `api/projects.ts`, `api/packages.ts`, `api/runs.ts` — i.e. every project/producer/render/publish/run call the dashboard makes) never sent `credentials: "include"` and never attached the `Authorization: Bearer <token>` header. Only the four auth-specific calls in `api/auth.ts` (`login`, `register`, `getMe`, `logout`) did.

Consequence: after a successful login, every other request the dashboard makes reaches the backend as an **anonymous** request. On the backend side:

- `POST /projects` → `current_user` resolves to `None` → the created project gets `owner_user_id=None` (never actually associated with the logged-in user).
- `GET /projects` → with no `current_user`, falls back to `project_manager.list_projects()` **unfiltered** — every visitor, logged in or not, sees every user's projects.
- `/projects/{id}/producer/run`, `/render/run`, `/render/status`, `/render/video`, `/publish/run`, `/publish/status`, `GET /runs/{run_id}`, and both SSE event streams (`/runs/{id}/events`, `/projects/{id}/events`) had **no ownership check and, in most cases, no `current_user` dependency at all** — they loaded the project/run by ID with zero authorization, so any caller who could see or guess a `project_id`/`run_id` (both are just UUIDs returned in API responses) could read another user's job status, generated video, and run results, or trigger production/render/publish runs against a project they don't own. This is an IDOR (insecure direct object reference) class finding across the majority of the app's actual functionality — login worked, but almost nothing behind it was actually gated by it.

So "authentication is not fully working end-to-end" was accurate, but the defect was not in the login/session code — it was that the session, once established, was never propagated to the requests that mattered, and several routers never checked ownership even when a session *was* propagated.

## Required Changes

1. **Frontend**: make `api/client.ts`'s shared request layer attach `Authorization: Bearer <token>` (from the same `localStorage` token `api/auth.ts` already uses) and `credentials: "include"` on every request, including the XHR upload path. Extracted the token-storage helpers into `api/token-storage.ts` so both `api/auth.ts` and `api/client.ts` can read them without a circular import.
2. **Backend**: give `producer.py`, `render.py`, `publish.py`, `runs.py`, and `events.py` the same ownership enforcement `projects.py` already had, reusing a shared `get_authorized_project` helper (extracted from `projects.py`'s existing `_get_authorized_project` into `web_api/project_authz.py`) rather than duplicating the logic five times. `runs.py`'s `GET /runs/{run_id}` and `events.py`'s `GET /runs/{run_id}/events` resolve the owning project via the `Run.project_id` field before authorizing, since a run_id alone isn't scoped to a caller.
3. Added regression tests (`tests/web_api/test_projects_multi_tenancy.py`) proving cross-user isolation on all of the newly-protected endpoints, following the existing test file's own Alpha/Beta multi-tenant fixture pattern.

No changes were made to password hashing, JWT logic, the user data model, CORS configuration, or the forgot-password/Google-OAuth "not configured" posture — those were already correct/intentionally incomplete per the task's own Phase 12/13 instructions.
