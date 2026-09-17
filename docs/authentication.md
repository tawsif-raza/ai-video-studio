# Authentication

Email/password authentication for AI Video Studio: architecture, endpoints, session mechanics, and environment configuration. See `docs/auth-audit.md` for the audit that preceded this doc and the root-cause analysis behind the fixes described here.

## Architecture

```
Browser (Next.js)                         API (FastAPI)
──────────────────                        ──────────────
AuthProvider (features/auth/AuthContext)
  ├─ holds user/token/isLoading state
  ├─ on mount: GET /auth/me  ────────────► auth/security.py: decode JWT
  │            (Authorization: Bearer)     web_api/dependencies.py:get_current_user
  └─ login/signup/logout ─────────────────► auth/user_store.py: UserStore
                                              ├─ LocalUserStore (dev, filesystem JSON)
                                              └─ PostgresUserStore (DB_HOST set: staging/prod)

ProtectedRoute (features/auth/ProtectedRoute)
  wraps the whole app (app/layout.tsx); redirects based on
  AuthContext's isAuthenticated, which is itself always derived
  from the backend's GET /auth/me response, never assumed locally.

api/client.ts (shared request layer: apiGet/apiPost/apiDelete/
apiPostForm/apiPostFormWithProgress — used by api/projects.ts,
api/packages.ts, api/runs.ts for all project/producer/render/
publish/run calls)
  attaches Authorization: Bearer <token> + credentials: "include"
  on every request, the same way api/auth.ts's own login/register/
  me/logout calls already did. Token comes from api/token-storage.ts.
```

Every project-scoped backend endpoint (`/projects*`, `/projects/{id}/producer|render|publish/*`, `/runs/{run_id}`, both SSE event streams) authorizes via a single shared helper, `web_api/project_authz.py:get_authorized_project`, so "who may touch this project" is decided in exactly one place. An unowned project (`owner_user_id=None` — legacy/anonymous) stays open to any caller; an owned project 404s (never 403, to avoid confirming existence) for anyone but its owner.

## Endpoints

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/auth/register` | public | creates user, sets session cookie + returns bearer token |
| POST | `/auth/login` | public | same response shape as register |
| GET | `/auth/me` | required | current user profile (password/salt stripped) |
| PATCH | `/auth/me` | required | update `full_name`/`preferences`/`api_keys` |
| PATCH | `/auth/me/password` | required | requires current password |
| POST | `/auth/logout` | public | clears `access_token`/`session_token` cookies |
| POST | `/auth/forgot-password` | public | neutral response; see Forgot Password below |
| POST | `/auth/reset-password` | public | single-use token, 1h expiry |
| * | `/projects*` | optional + ownership | anonymous access permitted only for unowned projects |
| * | `/projects/{id}/producer\|render\|publish/*` | optional + ownership | same rule |
| GET | `/runs/{run_id}` | optional + ownership | resolved via the run's `project_id` |
| GET | `/runs/{run_id}/events`, `/projects/{id}/events` | optional + ownership | SSE streams |

Every auth route is mounted at both `/auth/...` and `/api/auth/...` (`web_api/__init__.py`); the frontend uses the bare `/auth/...` form.

## Session Mechanism

JWT (HS256, `AUTH_SECRET_KEY`), 24h expiry by default (`ACCESS_TOKEN_EXPIRE_MINUTES`). Two things happen on every login/register:

1. The token is returned in the JSON body (`access_token`) — this is what the frontend actually uses. It's stored in `localStorage` (`studio_access_token`, `frontend/api/token-storage.ts`) and sent back as `Authorization: Bearer <token>` on every subsequent request.
2. The same token is also set as an `HttpOnly` cookie (`access_token`) — accepted by `get_current_user` as a fallback, but not relied on by the shipped frontend. It exists so a non-JS client (or a future server-rendered flow) can authenticate without touching `localStorage`.

`GET /auth/me` is the single source of truth for "is this session valid" — the frontend never infers authentication from local state alone.

## Cookie Behavior

`httponly=True`, `path="/"`, `max_age=86400` are fixed. `secure` and `samesite` are **environment-driven** (`config.py`: `resolve_cookie_secure`/`resolve_cookie_samesite`, applied in `web_api/routers/auth.py` via `_set_session_cookie`/`_clear_session_cookies`), because local dev, and a staging/production split where the Next.js frontend (Vercel) and this API (Railway) live on different sites, need different, browser-correct values:

| `ENVIRONMENT` | `COOKIE_SECURE` (default) | `COOKIE_SAMESITE` (default) | Why |
|---|---|---|---|
| `development` (local default) | `false` | `lax` | plain HTTP, same-site |
| `staging` / `production` | `true` | `none` | HTTPS, cross-site (Vercel ↔ Railway) — browsers only honor `SameSite=None` alongside `Secure` |

Both are overridable via the `COOKIE_SECURE`/`COOKIE_SAMESITE` env vars (e.g. a same-site staging/prod deployment can set `COOKIE_SAMESITE=lax` explicitly instead of taking the cross-site default) — but `config.py:validate_cookie_config` runs once at process startup and **raises immediately, refusing to start**, if `ENVIRONMENT` is `staging`/`production` and `COOKIE_SECURE` resolves to `false`, or if `COOKIE_SAMESITE=none` is ever paired with `COOKIE_SECURE=false` (browser-invalid regardless of environment). This cannot be bypassed by omission — leaving `COOKIE_SECURE` unset in production uses the safe default (`true`), and only an explicit, wrong override can trigger the failure.

This only affects the cookie fallback path; it never touches the `Authorization: Bearer <token>` flow the frontend actually relies on for every request (`frontend/api/client.ts`), which is unconditional and identical in every environment. See `tests/test_config_cookies.py` (resolver/validator unit tests) and `tests/web_api/test_auth_cookies.py` (live `Set-Cookie` header assertions in both configurations, plus a check that the bearer-token flow is unaffected).

## Frontend Auth State

`AuthContext` exposes `unknown` (⇒ `isLoading: true`) → `loading` → `authenticated` / `unauthenticated`, matching the task's required state machine. `ProtectedRoute` never renders protected content or redirects while `isLoading` is true, preventing both a content flash and a false redirect during the initial `GET /auth/me` round trip.

## Protected Routes

Frontend: everything except `/login`, `/signup`, `/forgot-password`, `/reset-password` requires `isAuthenticated`; unauthenticated visits redirect to `/login?next=<original path>` (open-redirect-safe: `sanitizeDestination` rejects protocol-relative and non-local targets).

Backend: frontend route guards are UX only — every project-scoped endpoint listed above enforces ownership server-side regardless of what the UI does (verified in `tests/web_api/test_projects_multi_tenancy.py`).

## Environment Configuration

| Variable | Purpose | Local default |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | frontend → backend base URL | `http://127.0.0.1:8000` (`frontend/.env.local`) |
| `DASHBOARD_CORS_ORIGINS` | comma-separated allowed origins | unset → `http://localhost:3000,http://127.0.0.1:3000` |
| `AUTH_SECRET_KEY` | JWT signing key | insecure dev default in `auth/security.py` — **must** be overridden outside local dev |
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `RESET_TOKEN_EXPIRE_MINUTES` | token lifetimes | 1440 / 60 |
| `DB_HOST` | selects `PostgresUserStore`/`PostgresRunRegistry` over the local filesystem/in-memory versions | unset locally |
| `ENVIRONMENT` | `development` / `staging` / `production` — drives cookie `Secure`/`SameSite` defaults (see Cookie Behavior) and gates `/auth/forgot-password`'s `reset_token` echo | `development` |
| `AUTH_DEV_MODE` | also gates the `/auth/forgot-password` `reset_token` echo, independent of `ENVIRONMENT` | `false` |
| `COOKIE_SECURE`, `COOKIE_SAMESITE` | explicit override of the session cookie's `Secure`/`SameSite` attributes; refuses to start (see Cookie Behavior) if this would leave `staging`/`production` with an insecure cookie | unset → environment-appropriate default |

No secrets are committed; all of the above are read from the process environment (`os.getenv`) with dev-safe defaults only where doing so can't leak into a real deployment.

### Local

`ai_video_studio/api_app.py` (`uvicorn`, port 8000) + `frontend` (`next dev`, port 3000). `LocalUserStore` (filesystem) and in-memory `RunRegistry` are used automatically since `DB_HOST` is unset. If port 3000 is already taken and Next.js falls back to another port, add that origin to `DASHBOARD_CORS_ORIGINS` or free port 3000 — the CORS allow-list does not include arbitrary local ports by default.

### Staging / Production

Set `ENVIRONMENT=staging` or `ENVIRONMENT=production`; `COOKIE_SECURE`/`COOKIE_SAMESITE` then default to `true`/`none` automatically (see Cookie Behavior) — no extra variable is required for a correct cookie, and the process refuses to start if something explicitly overrides `COOKIE_SECURE` back to `false`. Also set `DB_HOST` (plus the rest of the Postgres connection settings already used by `db/connection.py`) to switch to `PostgresUserStore`/`PostgresRunRegistry`; set `DASHBOARD_CORS_ORIGINS` to the real frontend origin(s) (Vercel preview/production URLs already match automatically via the built-in regex); set a real `AUTH_SECRET_KEY`.

## Google OAuth Status

**NOT CONFIGURED.** The "Continue with Google" button on the login page is a clearly-labeled placeholder (`LoginForm.tsx`'s `handleGoogleSignIn` shows an info notice: "Google Sign-In is a UI placeholder and will be enabled with OAuth setup in the next phase.") — it does not simulate authentication or issue a session. No OAuth client credentials or callback route exist in this codebase. Wiring real Google OAuth is additive: it can be added as a parallel path into the same `create_access_token`/cookie mechanism without redesigning email/password auth.

## Forgot Password Status

**Implemented, including real email delivery via Amazon SES**, gated entirely behind whether `SES_FROM_EMAIL` is configured (`auth/email.py:is_configured`).

- `POST /auth/forgot-password` always returns the same neutral message regardless of account existence, SES configuration, or delivery success/failure (account-enumeration protection — see `tests/web_api/test_auth_email.py`).
- When `SES_FROM_EMAIL` is set and the account exists, `auth/email.py:send_password_reset_email` sends the actual reset link via `boto3`'s SES client, using **only the process's default AWS credential chain** — the ECS task role in a deployed environment, or whatever AWS CLI/SSO session is active locally. No access key ID/secret is read, stored, or accepted anywhere in this path.
- The `reset_token` field in the JSON response is **independent** of email delivery and is only ever populated when `ENVIRONMENT != "production"` or `AUTH_DEV_MODE=true` — never in a real production response, whether or not SES is configured or the send succeeded (`tests/web_api/test_auth_email.py::test_reset_token_never_in_response_body_in_production_even_with_ses_configured`). `ForgotPasswordForm.tsx` labels this explicitly as a "Dev / Test Mode Token" when present, never a fake "email sent" confirmation.
- The reset link/token is never written to application logs, in any environment, by either the email module or the endpoint (`tests/auth/test_email.py`'s logging tests, `tests/web_api/test_auth_email.py::test_no_reset_link_or_token_reaches_the_logger`) — only the recipient's email address is logged, the same field the endpoint already logged before this change.
- An SES delivery failure (`EmailDeliveryError`) is caught and logged (recipient only) but never changes the HTTP response — a failure must not become an "this account exists but delivery broke" signal.
- If `SES_FROM_EMAIL` is unset (local dev's default), behavior is unchanged from before: no email is sent, and the dev-mode `reset_token` response field is the only way to complete the flow.

**IAM**: the API task role gets a single additional statement — `ses:SendEmail`, scoped to exactly the configured sending identity's ARN (`arn:aws:ses:<region>:<account>:identity/<from-email>`) — added only when `ses_from_email` is non-empty (`infra/modules/iam/main.tf`'s `dynamic "statement"` block). No `Resource: "*"`, no `ses:SendRawEmail`/`ses:SendTemplatedEmail` (not used by `auth/email.py`), and the statement is entirely absent from the policy (not just empty) when SES isn't configured.

**Configuration** (`infra/environments/production/variables.tf`): `ses_region` (default `ap-south-1`), `ses_from_email` (default `tawsifk35@gmail.com`, the verified identity), `frontend_base_url` (default the Vercel production alias, used to build an absolute clickable link — an email client can't resolve a relative path). None of these are secrets; they're plain ECS task environment variables (`infra/modules/ecs_api/main.tf`), same as `DASHBOARD_CORS_ORIGINS`.

## Testing

- Backend: `pytest tests/web_api/test_auth.py tests/web_api/test_projects_multi_tenancy.py` (37 + 11 tests) — register/login/me/update/password-change/logout/forgot/reset flows, plus cross-user ownership isolation across projects, media, packages, producer, render, publish, runs, and both SSE event streams.
- Backend cookie config: `pytest tests/test_config_cookies.py tests/web_api/test_auth_cookies.py` (12 + 6 tests) — `resolve_cookie_secure`/`resolve_cookie_samesite`/`validate_cookie_config` unit tests for every local/staging/production/override combination, plus live `Set-Cookie` header assertions for both a local-like and a production-like configuration (register, login, logout) and a check that the `Authorization`-header flow is unaffected by cookie config.
- Backend SES email: `pytest tests/auth/test_email.py tests/web_api/test_auth_email.py` (10 + 6 tests) — `is_configured`/`build_reset_link`/`send_password_reset_email` unit tests (mocked `boto3` client, no real AWS calls), plus `forgot_password` integration tests: email sent iff SES is configured and the account exists, response stays neutral on delivery failure, `reset_token` never present in a production response even with SES configured, and no reset link/token ever reaches the logger.
- Frontend: `npm test` (vitest) covers `LoginForm`, `SignupForm`, `ForgotPasswordForm`, `ResetPasswordForm`, `AuthContext`, `ProtectedRoute`, and `HeaderAuth`.
- Manual/real-browser verification performed for this change: register → logout → login → refresh (session persists) → navigate to a protected route while logged out (redirects to `/login?next=...`) → logout clears both the `localStorage` token and the session cookie (verified via a direct unauthenticated `fetch('/auth/me')` returning 401) → invalid credentials are rejected (verified via a DOM-event-level submission, bypassing Chrome's password-manager autofill, which otherwise silently overwrote a deliberately-wrong password with the browser's saved one during automated testing — a browser-autofill interaction, not an application bug).
