# Implementation Plan & Roadmap — AI Video Studio

**Current Status:** Planning & Governance Initialized  
**Repository State:** v1.1 Monorepo (Core Engines + FastAPI + Next.js App Router)  
**Governance:** Governed by [`AGENTS.md`](file:///C:/ai_video_studio/AGENTS.md). Strict sequential task execution only.

---

## Execution State

| Dimension | Current State |
| :--- | :--- |
| **Current Phase** | **Phase 2 — User Dashboard & Multi-Tenancy** |
| **Current Task** | `DASH-02` (User Profile & Account Settings UI) |
| **Completed Tasks** | `AUTH-01` (Login UI & Presentation Layer), `AUTH-02` (Signup UI & Registration Flow), `AUTH-03` (Backend User Model & Password Hashing Core), `AUTH-04` (Authentication API Endpoints), `AUTH-05` (Frontend Auth Context & Session Management), `AUTH-06` (Protected Routes and Auth Navigation Guard), `AUTH-07` (Password Recovery Flow & Reset UI), `DASH-01` (User-Associated Project Isolation in ProjectManager) |
| **In-Progress Task** | `DASH-02` (User Profile & Account Settings UI) |
| **Blocked Tasks** | None |
| **Last Validation Result** | Frontend Vitest: 24 passed (148 tests, 100%), ESLint: 0 errors, Next.js Build: Clean (10/10 pages), Backend Pytest: 788 passed, 25 skipped (100%) |

---

## Sequential Execution Protocol

1. **Only the first incomplete task** (`NOT_STARTED`) may be executed. The agent must never skip, parallelize, or jump ahead to future tasks.
2. **One task at a time**: Complete all implementation, validation, and acceptance criteria before updating status.
3. **Mandatory validation**: After code changes, execute the specified `Validation commands`.
4. **State synchronization**: Update this document (`Status`, `Execution State`, and `Task Log`) immediately upon completing each task.
5. If validation fails and cannot be fixed cleanly within task boundaries, mark the task `BLOCKED` and halt.

---

# Phase 1 — Authentication & Identity

### Task AUTH-01: Login UI and Presentation Layer
- **Task ID:** `AUTH-01`
- **Phase:** Phase 1 — Authentication
- **Title:** Login UI and Presentation Layer
- **Status:** `COMPLETED`
- **Objective:** Provide a cinematic, production-grade login page and client-side form interaction.
- **Context:** Milestone W7 placeholder indicated authentication is needed. The login view must serve as the primary entrypoint for studio creators without yet wiring real backend auth.
- **Requirements:**
  1. AI Video Studio branding and tagline (*"AI-powered video creation and production platform"*).
  2. Google sign-in button as UI placeholder.
  3. Email and password fields with inline validation.
  4. Password visibility toggle with accessible ARIA states.
  5. Placeholders for "Forgot password?" and "Sign up".
  6. Submitting valid input shows simulated loading and validation notice.
  7. Mobile, tablet, and desktop responsive layout.
- **Implementation Guidance:**
  - Build `LoginForm.tsx` in `frontend/features/auth/`.
  - Create desktop cinematic preview panel `AuthShowcase.tsx`.
  - Wire route `/login` in `frontend/app/login/page.tsx`.
  - Configure `AppShell.tsx` to bypass sidebar navigation on auth routes.
- **Allowed files/directories:**
  - `frontend/app/login/**`
  - `frontend/features/auth/**`
  - `frontend/components/layout/AppShell.tsx`
- **Restricted files/directories:**
  - `ai_video_studio/**`
  - `frontend/components/layout/Sidebar.tsx`
  - `frontend/features/dashboard/**`
- **Dependencies:** None
- **Acceptance Criteria:**
  - [x] `/login` renders responsive, cinematic dual-panel layout on desktop and focused form on mobile.
  - [x] Email format and required validations display clear error messages.
  - [x] Password visibility toggles between masked and plaintext.
  - [x] Google sign-in and recovery links display informative placeholder notices.
  - [x] Automated unit tests cover rendering, interactions, and validation states.
- **Validation Commands:**
  - `npm --prefix frontend run test`
  - `npm --prefix frontend run lint`
  - `npm --prefix frontend run build`
- **Completion Requirements:** All frontend tests pass and route builds statically without errors.

---

### Task AUTH-02: Signup UI and Client-Side Registration Flow
- **Task ID:** `AUTH-02`
- **Phase:** Phase 1 — Authentication
- **Title:** Signup UI and Client-Side Registration Flow
- **Status:** `COMPLETED`
- **Objective:** Implement the frontend registration interface matching the cinematic design language.
- **Context:** Users clicking "Sign up" from the login page need a dedicated `/signup` route with full validation and account creation form controls.
- **Requirements:**
  1. Register route at `frontend/app/signup/page.tsx`.
  2. Full name, email address, password, and confirm password fields.
  3. Real-time password strength meter / requirement checklist (minimum 8 chars, numbers, uppercase).
  4. Terms of Service & Privacy Policy agreement checkbox placeholder.
  5. Client-side validation ensuring passwords match and inputs meet constraints.
  6. Navigation link to return to `/login`.
  7. Prevent duplicate submission with loading state.
- **Implementation Guidance:**
  - Create `SignupForm.tsx` in `frontend/features/auth/`.
  - Reuse `AuthShowcase.tsx` or adapt for onboarding narrative.
  - Update `AppShell.tsx` auth route recognition to include `/signup`.
  - Add comprehensive unit tests in `SignupForm.test.tsx`.
- **Allowed files/directories:**
  - `frontend/app/signup/**`
  - `frontend/features/auth/**`
  - `frontend/components/layout/AppShell.tsx`
- **Restricted files/directories:**
  - `ai_video_studio/**`
  - `frontend/api/**`
- **Dependencies:** `AUTH-01`
- **Acceptance Criteria:**
  - [x] Accessible inputs with validation feedback.
  - [x] Password match validation works as user types and blurs.
  - [x] Password criteria checklist updates dynamically as user enters characters.
  - [x] Bidirectional navigation between `/login` and `/signup`.
  - [x] Unit tests verify all error conditions and successful submission simulation.
  - [x] Static build prerenders `/signup` with zero errors.
- **Validation Commands:**
  - `npm --prefix frontend run test`
  - `npm --prefix frontend run lint`
  - `npm --prefix frontend run build`
- **Completion Requirements:** Unit tests for `SignupForm` pass; page builds with zero errors.

---

### Task AUTH-03: Backend User Model & Password Hashing Core
- **Task ID:** `AUTH-03`
- **Phase:** Phase 1 — Authentication
- **Title:** Backend User Model & Password Hashing Core
- **Status:** `COMPLETED`
- **Objective:** Create typed user schemas, secure password hashing, and user persistence in the backend.
- **Context:** The backend currently has no user identity layer. Project data is saved globally to disk via `ProjectManager`. We need a modular user persistence module.
- **Requirements:**
  1. Define Pydantic user models (`User`, `UserCreate`, `UserInDB`, `UserResponse`) in `ai_video_studio/shared_core/contracts/user.py`.
  2. Create secure password hashing and verification utility (Argon2 or Bcrypt via `hashlib`/`passlib` or modern standard).
  3. Create an abstract user storage interface (`UserStore`) and local filesystem/JSON implementation that respects the `ProjectManager` file storage discipline.
  4. Ensure passwords are never stored in plaintext and never leaked in API models.
- **Implementation Guidance:**
  - Place core user contracts in `shared_core/contracts/user.py`.
  - Implement `ai_video_studio/auth/security.py` for token/hashing routines.
  - Implement `ai_video_studio/auth/user_store.py` for saving user accounts into a structured `users/` directory under `OUTPUT_DIR`.
  - Write isolated unit tests in `ai_video_studio/tests/auth/`.
- **Allowed files/directories:**
  - `ai_video_studio/shared_core/contracts/user.py`
  - `ai_video_studio/auth/**`
  - `ai_video_studio/tests/auth/**`
- **Restricted files/directories:**
  - `ai_video_studio/director_studio/**`
  - `ai_video_studio/producer_studio/**`
  - `ai_video_studio/execution_engine/**`
  - `frontend/**`
- **Dependencies:** `AUTH-02`
- **Acceptance Criteria:**
  - [x] Password hashing passes verification tests with salt.
  - [x] User records can be created, retrieved by email/ID, and updated safely.
  - [x] Sensitive hashes are stripped from `UserResponse`.
- **Validation Commands:**
  - `pytest ai_video_studio/tests/auth/`
  - `pytest`
- **Completion Requirements:** All auth unit tests pass; 100% regression suite passes.
- **Completion Summary:**
  - Enhanced `shared_core/contracts/user.py` with `User`, `UserBase`, `UserCreate`, `UserInDB`, and `UserResponse` contracts including email/name validation and `to_user()` / `to_response()` conversion methods.
  - Implemented `ai_video_studio/auth/security.py` with cryptographically secure PBKDF2-HMAC-SHA256 password hashing with random salt, constant-time verification, and PyJWT token encode/decode utilities.
  - Implemented `ai_video_studio/auth/user_store.py` with abstract `UserStore` interface and `LocalUserStore` persisting JSON records to `users/<id>/user.json`, adhering to `ProjectManager` directory and path safety conventions.
  - Added 23 unit tests in `ai_video_studio/tests/auth/` verifying contracts, hashing, token lifecycles, and storage CRUD; all 23 auth tests passed and full backend regression suite passed (750 passed, 25 skipped).

---

### Task AUTH-04: Authentication API Endpoints (Login, Register, Me, Logout)
- **Task ID:** `AUTH-04`
- **Phase:** Phase 1 — Authentication
- **Title:** Authentication API Endpoints (Login, Register, Me, Logout)
- **Status:** `COMPLETED`
- **Objective:** Expose secure HTTP endpoints in FastAPI for registration, token generation, and identity lookup.
- **Context:** Integrates the `UserStore` with `web_api` using JWT or secure HTTP-only session cookies.
- **Requirements:**
  1. `POST /api/auth/register` — registers user, validates email uniqueness, returns auth token or user profile.
  2. `POST /api/auth/login` — verifies credentials, issues JWT access token or session cookie.
  3. `GET /api/auth/me` — returns active user profile from auth token.
  4. `POST /api/auth/logout` — invalidates session/token.
  5. Add `get_current_user` FastAPI dependency in `web_api/dependencies.py`.
- **Implementation Guidance:**
  - Create `ai_video_studio/web_api/routers/auth.py`.
  - Register the auth router in `ai_video_studio/web_api/__init__.py`.
  - Add dependency in `ai_video_studio/web_api/dependencies.py`.
  - Unit and integration tests in `ai_video_studio/tests/web_api/test_auth.py`.
- **Allowed files/directories:**
  - `ai_video_studio/web_api/routers/auth.py`
  - `ai_video_studio/web_api/__init__.py`
  - `ai_video_studio/web_api/dependencies.py`
  - `ai_video_studio/tests/web_api/test_auth.py`
- **Restricted files/directories:**
  - `ai_video_studio/director_studio/**`
  - `ai_video_studio/producer_studio/**`
  - `frontend/**`
- **Dependencies:** `AUTH-03`
- **Acceptance Criteria:**
  - [x] Invalid credentials return 401 Unauthorized with standardized error envelope.
  - [x] Duplicate registration returns 409 Conflict.
  - [x] Protected endpoint returns current user when valid bearer token/cookie is provided.
- **Validation Commands:**
  - `pytest ai_video_studio/tests/web_api/test_auth.py`
  - `pytest`
- **Completion Requirements:** All web API auth tests pass; full backend test suite passes.
- **Completion Summary:**
  - Created [`ai_video_studio/web_api/routers/auth.py`](file:///C:/ai_video_studio/ai_video_studio/web_api/routers/auth.py) implementing `/register`, `/login`, `/me`, and `/logout` endpoints with OpenAPI documentation, dual mounting (`/api/auth` and `/auth`), input validation, and HTTP-only cookie support.
  - Added [`get_user_store`](file:///C:/ai_video_studio/ai_video_studio/web_api/dependencies.py), [`get_current_user`](file:///C:/ai_video_studio/ai_video_studio/web_api/dependencies.py), and [`get_optional_current_user`](file:///C:/ai_video_studio/ai_video_studio/web_api/dependencies.py) in [`ai_video_studio/web_api/dependencies.py`](file:///C:/ai_video_studio/ai_video_studio/web_api/dependencies.py) to validate bearer tokens and session cookies against `UserStore`.
  - Registered auth router in [`ai_video_studio/web_api/__init__.py`](file:///C:/ai_video_studio/ai_video_studio/web_api/__init__.py).
  - Authored comprehensive test suite in [`ai_video_studio/tests/web_api/test_auth.py`](file:///C:/ai_video_studio/ai_video_studio/tests/web_api/test_auth.py) with 16 tests covering registration, login, cookie persistence, token expiration, tampered tokens, and logout.
  - All 16 web API auth tests passed and full backend regression suite passed cleanly (766 passed, 25 skipped).

---

### Task AUTH-05: Frontend Auth Context & Session Management
- **Task ID:** `AUTH-05`
- **Phase:** Phase 1 — Authentication
- **Title:** Frontend Auth Context & Session Management
- **Status:** `COMPLETED`
- **Objective:** Connect the frontend login and signup forms to the FastAPI auth endpoints with reactive session state.
- **Context:** Replaces the placeholder simulated validation with real HTTP calls via `frontend/api/client.ts`.
- **Requirements:**
  1. Create `AuthContext` and `useAuth` hook in `frontend/features/auth/AuthContext.tsx`.
  2. Connect `LoginForm` and `SignupForm` to real authentication actions.
  3. Store auth token in secure storage (HTTP-only cookie or memory + refresh pattern).
  4. Provide reactive state: `user`, `isAuthenticated`, `isLoading`, `login`, `signup`, `logout`.
  5. Update `Header.tsx` to display authenticated user badge and sign-out action.
- **Implementation Guidance:**
  - Add auth client methods to `frontend/api/auth.ts`.
  - Wrap application in `AuthProvider` in `app/layout.tsx`.
  - Test with Vitest using mock API server or handlers.
- **Allowed files/directories:**
  - `frontend/features/auth/**`
  - `frontend/api/auth.ts`
  - `frontend/components/layout/Header.tsx`
  - `frontend/app/layout.tsx`
- **Restricted files/directories:**
  - `ai_video_studio/**`
- **Dependencies:** `AUTH-04`
- **Acceptance Criteria:**
  - [x] User can log in with valid credentials and receives active session.
  - [x] Invalid login displays API error message.
  - [x] Logout clears session state and redirects to `/login`.
- **Validation Commands:**
  - `npm --prefix frontend run test`
  - `npm --prefix frontend run lint`
  - `npm --prefix frontend run build`
- **Completion Requirements:** Frontend auth tests pass; Next.js build succeeds.
- **Completion Summary:**
  - Connected [`LoginForm.tsx`](file:///C:/ai_video_studio/frontend/features/auth/LoginForm.tsx) and [`SignupForm.tsx`](file:///C:/ai_video_studio/frontend/features/auth/SignupForm.tsx) to real authentication operations using `useAuth()` (`login` and `signup`), updating reactive session state, providing inline API error alerts, and redirecting to the studio on success.
  - Enhanced [`AuthContext.tsx`](file:///C:/ai_video_studio/frontend/features/auth/AuthContext.tsx) and [`api/auth.ts`](file:///C:/ai_video_studio/frontend/api/auth.ts) with resilient token storage, session initialization from stored tokens, reactive session state (`user`, `isAuthenticated`, `isLoading`), and full lifecycle methods (`login`, `signup`, `logout`, `refreshSession`).
  - Updated [`Header.tsx`](file:///C:/ai_video_studio/frontend/components/layout/Header.tsx) to display authenticated user badge with avatar/initials, full name, email, and a sign-out action calling `logout()` and navigating to `/login`, or a `Sign In` link when unauthenticated.
  - Wrapped root app tree with [`AuthProvider`](file:///C:/ai_video_studio/frontend/features/auth/AuthContext.tsx) in [`layout.tsx`](file:///C:/ai_video_studio/frontend/app/layout.tsx).
  - Authored comprehensive test suites in [`AuthContext.test.tsx`](file:///C:/ai_video_studio/frontend/features/auth/AuthContext.test.tsx) and [`HeaderAuth.test.tsx`](file:///C:/ai_video_studio/frontend/features/auth/HeaderAuth.test.tsx), and updated [`LoginForm.test.tsx`](file:///C:/ai_video_studio/frontend/features/auth/LoginForm.test.tsx) and [`SignupForm.test.tsx`](file:///C:/ai_video_studio/frontend/features/auth/SignupForm.test.tsx).
  - All 21 Vitest test files (121 tests) passed, ESLint passed with 0 errors, Next.js production build succeeded cleanly, and full backend regression suite passed (766 passed, 25 skipped).

---

### Task AUTH-06: Protected Routes and Auth Navigation Guard
- **Task ID:** `AUTH-06`
- **Phase:** Phase 1 — Authentication
- **Title:** Protected Routes and Auth Navigation Guard
- **Status:** `COMPLETED`
- **Objective:** Guard dashboard, projects, and studio workspaces from unauthenticated access.
- **Context:** Currently, visiting `/` or `/projects` is completely open.
- **Requirements:**
  1. Implement client/middleware route guard redirecting unauthenticated users to `/login?next=...`.
  2. Redirect authenticated users away from `/login` and `/signup` to `/`.
  3. Preserve intended destination in query parameter for post-login redirect.
- **Implementation Guidance:**
  - Use Next.js middleware or client route guard component in layout.
  - Verify seamless redirect behavior in tests.
- **Allowed files/directories:**
  - `frontend/middleware.ts` or `frontend/features/auth/ProtectedRoute.tsx`
  - `frontend/app/**`
- **Restricted files/directories:**
  - `ai_video_studio/**`
- **Dependencies:** `AUTH-05`
- **Acceptance Criteria:**
  - [x] Unauthenticated access to `/projects` redirects to `/login`.
  - [x] Authenticated access to `/login` redirects to `/`.
- **Validation Commands:**
  - `npm --prefix frontend run test`
  - `npm --prefix frontend run build`
- **Completion Requirements:** Navigation guard passes tests.
- **Completion Summary:**
  - Implemented [`ProtectedRoute.tsx`](file:///C:/ai_video_studio/frontend/features/auth/ProtectedRoute.tsx) providing route classification (`isAuthRoute`), destination sanitization (`sanitizeDestination`), query parameter preservation (`?next=` / `?redirect=`), loading barrier preventing content flashes, and dynamic navigation guards.
  - Integrated [`ProtectedRoute`](file:///C:/ai_video_studio/frontend/features/auth/ProtectedRoute.tsx) inside [`RootLayout`](file:///C:/ai_video_studio/frontend/app/layout.tsx), automatically guarding all private studio areas (`/`, `/projects`, `/settings`, etc.) while ensuring unauthenticated visitors access `/login` and `/signup`.
  - Harmonized [`LoginForm.tsx`](file:///C:/ai_video_studio/frontend/features/auth/LoginForm.tsx) and [`SignupForm.tsx`](file:///C:/ai_video_studio/frontend/features/auth/SignupForm.tsx) to respect sanitized destination parameters for post-login redirects.
  - Enhanced [`AuthContext.tsx`](file:///C:/ai_video_studio/frontend/features/auth/AuthContext.tsx) to distinguish definitive authentication rejections (401/403) from temporary network glitches.
  - Authored comprehensive test suite in [`ProtectedRoute.test.tsx`](file:///C:/ai_video_studio/frontend/features/auth/ProtectedRoute.test.tsx) with 14 unit tests covering unauthenticated redirects, authenticated redirects, loading screen rendering, destination sanitization, and public route overrides.
  - All 22 Vitest test files (135 tests) passed, ESLint passed with 0 errors, Next.js production build succeeded cleanly, and full backend regression suite passed (766 passed, 25 skipped).

---

### Task AUTH-07: Password Recovery Flow & Reset UI
- **Task ID:** `AUTH-07`
- **Phase:** Phase 1 — Authentication
- **Title:** Password Recovery Flow & Reset UI
- **Status:** `COMPLETED`
- **Objective:** Implement the forgot password request and tokenized reset interface.
- **Context:** Replaces the placeholder notice on "Forgot password?".
- **Requirements:**
  1. Route `/forgot-password` with email recovery form.
  2. Route `/reset-password` accepting token from URL query.
  3. Backend token generation with expiration (time-bounded crypto token).
  4. Password reset confirmation and automatic redirect to login.
- **Implementation Guidance:**
  - Add recovery endpoints in `ai_video_studio/web_api/routers/auth.py`.
  - Create recovery views in `frontend/features/auth/`.
- **Allowed files/directories:**
  - `frontend/app/forgot-password/**`
  - `frontend/app/reset-password/**`
  - `frontend/features/auth/**`
  - `ai_video_studio/web_api/routers/auth.py`
- **Restricted files/directories:**
  - Core studio engines
- **Dependencies:** `AUTH-06`
- **Acceptance Criteria:**
  - [x] Requesting reset creates valid expiration token.
  - [x] Submitting new password updates user credentials and revokes token.
- **Validation Commands:**
  - `pytest ai_video_studio/tests/web_api/test_auth.py`
  - `npm --prefix frontend run test`
  - `npm --prefix frontend run build`
- **Completion Requirements:** End-to-end password reset flow verified.
- **Completion Summary:**
  - Enhanced [`ai_video_studio/auth/security.py`](file:///C:/ai_video_studio/ai_video_studio/auth/security.py) with scoped password recovery JWT creation and verification (`create_password_reset_token`, `decode_password_reset_token`), embedding user ID, email, expiration, and password hash fingerprint for stateless single-use token revocation.
  - Added `/forgot-password` and `/reset-password` endpoints in [`ai_video_studio/web_api/routers/auth.py`](file:///C:/ai_video_studio/ai_video_studio/web_api/routers/auth.py), implementing email validation, neutral response preventing account enumeration, expiration checking, single-use validation, and secure password updates via `LocalUserStore`.
  - Added dependency guard in [`ai_video_studio/web_api/dependencies.py`](file:///C:/ai_video_studio/ai_video_studio/web_api/dependencies.py) ensuring password reset tokens cannot be misused as access tokens for protected API routes.
  - Updated [`frontend/features/auth/ProtectedRoute.tsx`](file:///C:/ai_video_studio/frontend/features/auth/ProtectedRoute.tsx) and [`frontend/components/layout/AppShell.tsx`](file:///C:/ai_video_studio/frontend/components/layout/AppShell.tsx) to classify `/forgot-password` and `/reset-password` as auth routes and sanitize redirects.
  - Connected [`LoginForm.tsx`](file:///C:/ai_video_studio/frontend/features/auth/LoginForm.tsx) "Forgot password?" directly to `/forgot-password`.
  - Implemented [`ForgotPasswordForm.tsx`](file:///C:/ai_video_studio/frontend/features/auth/ForgotPasswordForm.tsx) and `/forgot-password` page with email validation, neutral notification banner, and non-production dev-token assistance.
  - Implemented [`ResetPasswordForm.tsx`](file:///C:/ai_video_studio/frontend/features/auth/ResetPasswordForm.tsx) and `/reset-password` page with token query parsing inside Next.js `<Suspense>` boundary, password requirement checklist, password confirmation matching, visibility toggles, and post-reset login redirection.
  - Added unit test suites in [`ai_video_studio/tests/web_api/test_auth.py`](file:///C:/ai_video_studio/ai_video_studio/tests/web_api/test_auth.py), [`ForgotPasswordForm.test.tsx`](file:///C:/ai_video_studio/frontend/features/auth/ForgotPasswordForm.test.tsx), and [`ResetPasswordForm.test.tsx`](file:///C:/ai_video_studio/frontend/features/auth/ResetPasswordForm.test.tsx), plus updated [`ProtectedRoute.test.tsx`](file:///C:/ai_video_studio/frontend/features/auth/ProtectedRoute.test.tsx) and [`LoginForm.test.tsx`](file:///C:/ai_video_studio/frontend/features/auth/LoginForm.test.tsx).
  - All 27 web API auth tests passed, full backend pytest suite passed (777 passed, 25 skipped), all 24 frontend Vitest suites passed (148 tests), ESLint passed with 0 errors, and Next.js production build succeeded with 10 static/dynamic routes generated cleanly.

---

# Phase 2 — User Dashboard & Multi-Tenancy

### Task DASH-01: User-Associated Project Isolation in ProjectManager
- **Task ID:** `DASH-01`
- **Phase:** Phase 2 — User Dashboard
- **Title:** User-Associated Project Isolation in ProjectManager
- **Status:** `COMPLETED` (2026-09-06)
- **Objective:** Upgrade `ProjectManager` to associate projects with specific `user_id`s, preventing cross-user data leakage.
- **Context:** Projects in `OUTPUT_DIR` are currently saved flatly by project ID. We must ensure every project manifest and path is scoped to its owner.
- **Requirements:**
  1. Add `owner_user_id` field to `Project` contract in `shared_core/contracts/project.py`.
  2. Update `ProjectManager.create_project` to accept and record `owner_user_id`.
  3. Update `ProjectManager.list_projects` to filter by `owner_user_id` (with backward compatibility for existing unassigned projects).
  4. Ensure authorization checks in `web_api/routers/projects.py` prevent accessing projects owned by another user.
- **Implementation Guidance:**
  - Keep changes strictly additive to `project_manager/manager.py`.
  - Update `web_api/routers/projects.py` to extract `current_user.id` and pass to `ProjectManager`.
  - Update backend tests to verify ownership isolation.
- **Allowed files/directories:**
  - `ai_video_studio/shared_core/contracts/project.py`
  - `ai_video_studio/project_manager/manager.py`
  - `ai_video_studio/web_api/routers/projects.py`
  - `ai_video_studio/tests/**`
- **Restricted files/directories:**
  - Studio planning agents
  - Execution engine internals
- **Dependencies:** `AUTH-06`
- **Acceptance Criteria:**
  - [x] User A cannot view, modify, delete, or run jobs on User B's projects.
  - [x] Project listing only returns projects belonging to the requesting user.
- **Validation Commands:**
  - `pytest ai_video_studio/tests/project_manager/`
  - `pytest ai_video_studio/tests/web_api/`
  - `pytest`
- **Completion Requirements:** Multi-tenant project isolation passes tests without regressions.
- **Completion Summary:**
  - Added [`ai_video_studio/shared_core/contracts/project.py`](file:///C:/ai_video_studio/ai_video_studio/shared_core/contracts/project.py) defining `Project` with optional `owner_user_id: Optional[str] = None` and `ProjectState` enum, re-exported across [`project_manager/project.py`](file:///C:/ai_video_studio/ai_video_studio/project_manager/project.py) and [`shared_core/contracts/__init__.py`](file:///C:/ai_video_studio/ai_video_studio/shared_core/contracts/__init__.py) for 100% backward compatibility.
  - Updated [`ProjectManager`](file:///C:/ai_video_studio/ai_video_studio/project_manager/manager.py):
    - `create_project(owner_user_id=...)` records and persists the user identity.
    - `load_project(project_id, owner_user_id=...)` enforces tenant ownership checking, raising `PermissionError` when accessed by another tenant while gracefully allowing unassigned projects and internal execution.
    - `list_projects(owner_user_id=..., include_unassigned=...)` scopes listings strictly to the requesting user while supporting legacy unassigned inclusion.
    - `delete_project(project_id, owner_user_id=...)` validates authorization prior to directory removal.
  - Updated [`ai_video_studio/web_api/routers/projects.py`](file:///C:/ai_video_studio/ai_video_studio/web_api/routers/projects.py):
    - Added `_get_authorized_project` helper returning 404 (IDOR-safe enumeration prevention) when unauthenticated or unauthorized users attempt to read or modify a project owned by another user.
    - Wired `current_user` into `create_project` (`POST /projects`), `list_projects` (`GET /projects`), `get_project` (`GET /projects/{id}`), `delete_project` (`DELETE /projects/{id}`), media endpoints (`/media`), bulk media deletion, and package endpoints (`/production-package`, `/producer-package`).
  - Added unit test suites in [`test_manager_multi_tenancy.py`](file:///C:/ai_video_studio/ai_video_studio/tests/project_manager/test_manager_multi_tenancy.py) (5 tests) and [`test_projects_multi_tenancy.py`](file:///C:/ai_video_studio/ai_video_studio/tests/web_api/test_projects_multi_tenancy.py) (6 tests).
  - Validation passed: 105 project manager tests passed, 152 web API tests passed, 788 full backend tests passed (25 skipped, 0 regressions), 24 frontend test files passed (148 tests, 0 failures), ESLint passed (0 errors), Next.js build clean (10/10 routes).

---

### Task DASH-02: User Profile & Account Settings UI
- **Task ID:** `DASH-02`
- **Phase:** Phase 2 — User Dashboard
- **Title:** User Profile & Account Settings UI
- **Status:** `NOT_STARTED`
- **Objective:** Transform `/settings` from a placeholder into a functional user profile, security, and preferences manager.
- **Context:** `frontend/app/settings/page.tsx` is currently an explicit placeholder card.
- **Requirements:**
  1. Profile tab: display user name, email, account creation date.
  2. Security tab: change password form with validation.
  3. API keys tab: optional user-provided API key overrides (e.g. personal Gemini/OpenAI keys).
  4. Preferences: dark mode toggle, default video export aspect ratio (16:9 vs 9:16).
- **Implementation Guidance:**
  - Create modular tabs under `frontend/features/settings/`.
  - Wire to `GET/PATCH /api/auth/me` endpoints.
- **Allowed files/directories:**
  - `frontend/app/settings/**`
  - `frontend/features/settings/**`
  - `ai_video_studio/web_api/routers/auth.py`
- **Restricted files/directories:**
  - Core engines
- **Dependencies:** `DASH-01`
- **Acceptance Criteria:**
  - Profile updates successfully reflect in UI and persist in user record.
  - Password change requires current password verification.
- **Validation Commands:**
  - `npm --prefix frontend run test`
  - `npm --prefix frontend run build`
- **Completion Requirements:** Settings interface is fully operational and tested.

---

# Phase 3 — Subscription System

### Task SUBS-01: Subscription Plans & Entitlements Specification
- **Task ID:** `SUBS-01`
- **Phase:** Phase 3 — Subscription System
- **Title:** Subscription Plans & Entitlements Specification
- **Status:** `NOT_STARTED`
- **Objective:** Define tiers, quotas, and feature flags in the shared core contract layer.
- **Context:** Establishes tiers: `FREE`, `CREATOR`, `STUDIO_PRO`.
- **Requirements:**
  1. Typed contracts in `shared_core/contracts/subscription.py`:
     - `PlanTier` enum (`free`, `creator`, `studio_pro`).
     - `Entitlements` model: `max_projects`, `max_monthly_renders`, `max_render_resolution`, `watermark_enabled`, `concurrency_limit`.
     - `SubscriptionState` model: `tier`, `status`, `current_period_end`, `cancel_at_period_end`.
  2. Default free tier entitlements configured for all newly registered users.
  3. Entitlement evaluation utility in `ai_video_studio/billing/entitlements.py`.
- **Implementation Guidance:**
  - Define contracts cleanly in `shared_core/contracts/`.
  - Create entitlement verification service.
- **Allowed files/directories:**
  - `ai_video_studio/shared_core/contracts/subscription.py`
  - `ai_video_studio/billing/**`
  - `ai_video_studio/tests/billing/**`
- **Restricted files/directories:**
  - Studio planning agents
- **Dependencies:** `DASH-01`
- **Acceptance Criteria:**
  - Entitlement checker accurately determines whether a user can create another project or render in 4K.
- **Validation Commands:**
  - `pytest ai_video_studio/tests/billing/`
- **Completion Requirements:** Unit tests verify all plan boundaries and limits.

---

### Task SUBS-02: Usage Tracking, Quotas & Generation Guardrails
- **Task ID:** `SUBS-02`
- **Phase:** Phase 3 — Subscription System
- **Title:** Usage Tracking, Quotas & Generation Guardrails
- **Status:** `NOT_STARTED`
- **Objective:** Enforce subscription quotas on Director, Producer, and Execution Engine runs.
- **Context:** Users on the free tier must not exceed monthly render limits or trigger 4K rendering without an upgraded plan.
- **Requirements:**
  1. Track usage counters: `monthly_render_count`, `monthly_director_runs`.
  2. Add pre-flight entitlement check in `web_api/routers/director.py` and `web_api/routers/render.py`.
  3. Return standardized 402 Payment Required or 403 Forbidden with upgrade prompt when limits are exceeded.
- **Implementation Guidance:**
  - Add middleware or dependency checking entitlements before starting runs.
- **Allowed files/directories:**
  - `ai_video_studio/billing/**`
  - `ai_video_studio/web_api/routers/render.py`
  - `ai_video_studio/web_api/routers/director.py`
  - `ai_video_studio/web_api/dependencies.py`
- **Restricted files/directories:**
  - Core engine controllers (enforce at API boundary, not engine core)
- **Dependencies:** `SUBS-01`
- **Acceptance Criteria:**
  - Over-quota user requests are rejected before expensive render or LLM processes start.
- **Validation Commands:**
  - `pytest ai_video_studio/tests/web_api/`
  - `pytest`
- **Completion Requirements:** Quota enforcement verified via automated tests.

---

### Task SUBS-03: Frontend Pricing & Subscription Management UI
- **Task ID:** `SUBS-03`
- **Phase:** Phase 3 — Subscription System
- **Title:** Frontend Pricing & Subscription Management UI
- **Status:** `NOT_STARTED`
- **Objective:** Build the pricing comparison page, upgrade modals, and billing management dashboard.
- **Context:** Users need clear visibility into their current plan, remaining quotas, and upgrade options.
- **Requirements:**
  1. Route `/pricing` displaying Free, Creator, and Studio Pro tiers.
  2. Usage meter component on Dashboard showing remaining renders for the billing cycle.
  3. Upgrade modal triggered when hitting quota limits in the studio.
- **Implementation Guidance:**
  - Create `frontend/app/pricing/page.tsx`.
  - Create `frontend/features/billing/` components.
- **Allowed files/directories:**
  - `frontend/app/pricing/**`
  - `frontend/features/billing/**`
  - `frontend/features/dashboard/**`
- **Restricted files/directories:**
  - `ai_video_studio/**`
- **Dependencies:** `SUBS-02`
- **Acceptance Criteria:**
  - Pricing page presents clear tier comparison.
  - Usage progress bars reflect user quota state accurately.
- **Validation Commands:**
  - `npm --prefix frontend run test`
  - `npm --prefix frontend run build`
- **Completion Requirements:** Frontend billing components pass tests.

---

# Phase 4 — Payments

### Task PAY-01: Payment Gateway Integration & Checkout Sessions
- **Task ID:** `PAY-01`
- **Phase:** Phase 4 — Payments
- **Title:** Payment Gateway Integration & Checkout Sessions
- **Status:** `NOT_STARTED`
- **Objective:** Integrate Stripe/payment provider checkout session creation.
- **Context:** Enables creators to upgrade from Free to Creator or Studio Pro via hosted checkout.
- **Requirements:**
  1. Payment provider service wrapper in `ai_video_studio/billing/stripe_client.py`.
  2. `POST /api/billing/checkout-session` endpoint returning secure checkout URL.
  3. Support monthly and annual billing cycles.
  4. Pass user ID and plan tier in checkout metadata.
- **Implementation Guidance:**
  - Configure via environment variables (`STRIPE_API_KEY`, `STRIPE_WEBHOOK_SECRET`).
  - Provide mock payment provider in test suite.
- **Allowed files/directories:**
  - `ai_video_studio/billing/**`
  - `ai_video_studio/web_api/routers/billing.py`
  - `ai_video_studio/tests/billing/**`
- **Restricted files/directories:**
  - Core studio engines
- **Dependencies:** `SUBS-03`
- **Acceptance Criteria:**
  - Checkout session endpoint returns valid session ID and checkout URL.
  - Missing or invalid credentials handled gracefully with diagnostic errors.
- **Validation Commands:**
  - `pytest ai_video_studio/tests/billing/`
- **Completion Requirements:** Checkout creation tested with mock provider.

---

### Task PAY-02: Webhook Processing & Entitlement Reconciliation
- **Task ID:** `PAY-02`
- **Phase:** Phase 4 — Payments
- **Title:** Webhook Processing & Entitlement Reconciliation
- **Status:** `NOT_STARTED`
- **Objective:** Securely process payment webhooks to upgrade, renew, and cancel subscriptions.
- **Context:** Payment confirmation happens asynchronously via provider webhooks.
- **Requirements:**
  1. `POST /api/billing/webhooks` endpoint with cryptographic signature verification.
  2. Handle events:
     - `checkout.session.completed` -> activate subscription.
     - `invoice.paid` -> renew billing cycle and reset usage quotas.
     - `invoice.payment_failed` -> mark past-due and notify user.
     - `customer.subscription.deleted` -> downgrade to free tier.
  3. Idempotent webhook processing to prevent duplicate quota resets.
- **Implementation Guidance:**
  - Verify raw signature header before payload parsing.
  - Store processed webhook IDs to guarantee idempotency.
- **Allowed files/directories:**
  - `ai_video_studio/billing/**`
  - `ai_video_studio/web_api/routers/billing.py`
- **Restricted files/directories:**
  - Core studio engines
- **Dependencies:** `PAY-01`
- **Acceptance Criteria:**
  - Invalid webhook signatures rejected with 400.
  - Successful checkout immediately unlocks paid entitlements.
- **Validation Commands:**
  - `pytest ai_video_studio/tests/billing/`
- **Completion Requirements:** Webhook handlers pass automated event tests.

---

### Task PAY-03: Customer Portal & Subscription Cancellation Flow
- **Task ID:** `PAY-03`
- **Phase:** Phase 4 — Payments
- **Title:** Customer Portal & Subscription Cancellation Flow
- **Status:** `NOT_STARTED`
- **Objective:** Allow users to manage invoices, payment methods, and cancel/downgrade subscriptions.
- **Context:** Self-service billing portal is mandatory for SaaS operations.
- **Requirements:**
  1. `POST /api/billing/portal-session` generating customer portal link.
  2. Frontend button in Settings -> Billing to access portal.
  3. Grace period handling when a subscription is set to cancel at period end.
- **Implementation Guidance:**
  - Wire to Stripe Customer Portal API.
- **Allowed files/directories:**
  - `ai_video_studio/billing/**`
  - `frontend/features/billing/**`
  - `frontend/app/settings/**`
- **Dependencies:** `PAY-02`
- **Acceptance Criteria:**
  - Portal session redirects correctly.
  - Canceled subscriptions retain paid access until period expiration.
- **Validation Commands:**
  - `pytest ai_video_studio/tests/billing/`
  - `npm --prefix frontend run test`
- **Completion Requirements:** Customer billing lifecycle complete.

---

# Phase 5 — AI Video Production Pipeline Integration

### Task PROD-01: Web Workspace Full Pipeline Execution Wiring
- **Task ID:** `PROD-01`
- **Phase:** Phase 5 — AI Video Production
- **Title:** Web Workspace Full Pipeline Execution Wiring
- **Status:** `NOT_STARTED`
- **Objective:** Connect the complete Director -> Producer -> Execution -> Publishing pipeline smoothly within the web UI.
- **Context:** Individual run buttons exist in tabs; users need an automated "Full Run" or step-by-step wizard option in the frontend.
- **Requirements:**
  1. Sequential multi-stage trigger option: runs Director, loads assets, runs Producer, compiles Execution Engine.
  2. Unified progress indicator across all 4 stages.
  3. Retain manual human checkpoint between Director and Producer (allowing asset review/upload).
- **Implementation Guidance:**
  - Add pipeline orchestration runner in `frontend/features/projects/ProjectWorkspace.tsx`.
- **Allowed files/directories:**
  - `frontend/features/projects/**`
  - `frontend/hooks/**`
- **Restricted files/directories:**
  - Backend core engines
- **Dependencies:** `DASH-01`
- **Acceptance Criteria:**
  - Stage transitions update live via SSE without page reload.
  - Clear alerts when human media upload is required.
- **Validation Commands:**
  - `npm --prefix frontend run test`
  - `npm --prefix frontend run build`
- **Completion Requirements:** Frontend workspace multi-stage run passes tests.

---

### Task PROD-02: Video Generation Engine Real Provider Adapter (Google Veo)
- **Task ID:** `PROD-02`
- **Phase:** Phase 5 — AI Video Production
- **Title:** Video Generation Engine Real Provider Adapter (Google Veo)
- **Status:** `NOT_STARTED`
- **Objective:** Connect the existing `video_generation_engine` to the live Google Veo / Gemini API, replacing the `StubProvider` when configured.
- **Context:** Documented in `ARCHITECTURE.md` §25.15. `StubProvider` is currently tested; real provider integration needs secure API key integration and error handling.
- **Requirements:**
  1. Implement `GoogleVeoProvider` conforming to `VideoGenerationProvider` contract.
  2. Add budget/quota guardrails to prevent accidental quota exhaustion.
  3. Preflight check verifying video generation credits/keys.
  4. Postflight check validating generated MP4 stream parameters.
- **Implementation Guidance:**
  - Implement in `ai_video_studio/video_generation_engine/providers/google_veo.py`.
  - Ensure provider registry falls back gracefully if key is missing.
- **Allowed files/directories:**
  - `ai_video_studio/video_generation_engine/**`
  - `ai_video_studio/tests/**`
- **Restricted files/directories:**
  - Director Studio core
  - Producer Studio core
- **Dependencies:** `PROD-01`
- **Acceptance Criteria:**
  - Veo provider formats prompts correctly according to API specification.
  - Stub provider remains functional as a zero-cost local test target.
- **Validation Commands:**
  - `pytest ai_video_studio/tests/test_video_generation_google_veo_provider.py`
  - `pytest`
- **Completion Requirements:** Video generation tests pass cleanly.

---

# Phase 6 — Job Processing & Asynchronous Architecture

### Task JOB-01: Asynchronous Task Broker & Persistent Job Queue
- **Task ID:** `JOB-01`
- **Phase:** Phase 6 — Job Processing
- **Title:** Asynchronous Task Broker & Persistent Job Queue
- **Status:** `NOT_STARTED`
- **Objective:** Replace in-memory `RunRegistry` with a durable distributed job queue (Redis / Celery or ARQ).
- **Context:** `DEPLOYMENT.md` explicitly highlights that in-memory run tracking restricts backend to 1 replica. A shared queue allows multi-replica scaling.
- **Requirements:**
  1. Durable task broker interface (`JobQueue`).
  2. Redis-backed job state persistence and event publishing.
  3. Background worker process (`worker.py`) that picks up render and LLM jobs.
  4. Maintain identical SSE event format for frontend compatibility.
- **Implementation Guidance:**
  - Implement in `ai_video_studio/queue/`.
  - Connect `web_api/routers/` to dispatch tasks to queue instead of local background tasks.
- **Allowed files/directories:**
  - `ai_video_studio/queue/**`
  - `ai_video_studio/web_api/run_registry.py`
  - `ai_video_studio/web_api/dependencies.py`
- **Restricted files/directories:**
  - Core studio planning agents
- **Dependencies:** `PROD-02`
- **Acceptance Criteria:**
  - API restart does not lose status of ongoing or completed background jobs.
  - Multiple API workers can stream SSE progress for jobs run on any worker.
- **Validation Commands:**
  - `pytest ai_video_studio/tests/queue/`
  - `pytest`
- **Completion Requirements:** Durable queue passes multi-process test suite.

---

### Task JOB-02: Job Cancellation, Dead-Letter Queue & Retries
- **Task ID:** `JOB-02`
- **Phase:** Phase 6 — Job Processing
- **Title:** Job Cancellation, Dead-Letter Queue & Retries
- **Status:** `NOT_STARTED`
- **Objective:** Provide robust cancellation and retry management for long-running renders and video generation.
- **Context:** FFmpeg renders can take minutes. Users must be able to cancel an active render, and unexpected crashes must retry cleanly.
- **Requirements:**
  1. `POST /api/runs/{id}/cancel` endpoint that sends SIGTERM to running FFmpeg sub-processes.
  2. Retry policy with exponential backoff for transient LLM/API failures.
  3. Dead-letter queue (DLQ) for poisoned tasks with detailed diagnostic logs.
- **Implementation Guidance:**
  - Connect cancellation signal to `FFmpegExecutor`.
- **Allowed files/directories:**
  - `ai_video_studio/queue/**`
  - `ai_video_studio/execution_engine/ffmpeg_executor.py`
  - `ai_video_studio/web_api/routers/runs.py`
- **Dependencies:** `JOB-01`
- **Acceptance Criteria:**
  - Canceling a run immediately terminates the child FFmpeg process and frees system resources.
- **Validation Commands:**
  - `pytest ai_video_studio/tests/queue/`
- **Completion Requirements:** Cancellation and retry tests pass.

---

# Phase 7 — Storage & Asset Management

### Task STOR-01: Cloud Object Storage Provider Abstraction (S3/GCS/R2)
- **Task ID:** `STOR-01`
- **Phase:** Phase 7 — Storage
- **Title:** Cloud Object Storage Provider Abstraction (S3/GCS/R2)
- **Status:** `NOT_STARTED`
- **Objective:** Move media uploads, generated video clips, and final rendered MP4s from ephemeral container disk to durable cloud object storage.
- **Context:** `DEPLOYMENT.md` notes that Railway container disk is ephemeral. Storing large video files in S3/Cloudflare R2 is necessary for production survival.
- **Requirements:**
  1. `StorageProvider` interface with local disk (dev) and S3/R2 (prod) implementations.
  2. Pre-signed upload URLs for client-side direct multipart media upload.
  3. Pre-signed download/streaming URLs for rendered videos.
  4. Adapt `ProjectManager` to store binary media in object storage while retaining JSON manifests.
- **Implementation Guidance:**
  - Implement in `ai_video_studio/storage/`.
  - Maintain backward compatibility for local filesystem during unit tests.
- **Allowed files/directories:**
  - `ai_video_studio/storage/**`
  - `ai_video_studio/project_manager/manager.py`
  - `ai_video_studio/web_api/routers/projects.py`
- **Restricted files/directories:**
  - Core studio planning agents
- **Dependencies:** `JOB-02`
- **Acceptance Criteria:**
  - Media files upload directly to object storage; manifests reference cloud keys.
  - Local tests run seamlessly against mock storage.
- **Validation Commands:**
  - `pytest ai_video_studio/tests/storage/`
  - `pytest`
- **Completion Requirements:** Storage abstraction tests pass with 0 regressions.

---

### Task STOR-02: Asset Deduplication, Cleanup & Quota Management
- **Task ID:** `STOR-02`
- **Phase:** Phase 7 — Storage
- **Title:** Asset Deduplication, Cleanup & Quota Management
- **Status:** `NOT_STARTED`
- **Objective:** Implement content-addressable storage deduplication and automatic cleanup of abandoned intermediate renders.
- **Context:** Video rendering generates large intermediate segments (`.ts`, `.mp4`). Unused renders must be pruned to manage storage bills.
- **Requirements:**
  1. Checksum-based media deduplication on upload.
  2. Background retention policy cleaner for temporary filtergraph scratch files.
  3. Total user storage usage calculation and quota enforcement.
- **Implementation Guidance:**
  - SHA256 checksum check before creating duplicate media objects.
- **Allowed files/directories:**
  - `ai_video_studio/storage/**`
  - `ai_video_studio/billing/**`
- **Dependencies:** `STOR-01`
- **Acceptance Criteria:**
  - Duplicate file uploads reuse existing storage objects.
  - Scratch render directories cleaned up post-render.
- **Validation Commands:**
  - `pytest ai_video_studio/tests/storage/`
- **Completion Requirements:** Cleanup and deduplication verified.

---

# Phase 8 — Production Infrastructure & Reliability

### Task INFRA-01: Environment Configuration, Secret Management & Validation
- **Task ID:** `INFRA-01`
- **Phase:** Phase 8 — Production Infrastructure
- **Title:** Environment Configuration, Secret Management & Validation
- **Status:** `NOT_STARTED`
- **Objective:** Consolidate configuration management and enforce strict startup validation.
- **Context:** Ensures all required production environment variables (API keys, CORS origins, secrets) are validated at boot.
- **Requirements:**
  1. Centralized Pydantic `Settings` model in `ai_video_studio/config.py`.
  2. Startup preflight check failing immediately with clear diagnostics if critical keys are missing.
  3. Mask all secrets in logging output.
- **Implementation Guidance:**
  - Enhance `config.py` with typed validators.
- **Allowed files/directories:**
  - `ai_video_studio/config.py`
  - `ai_video_studio/utils/logger.py`
- **Dependencies:** `STOR-02`
- **Acceptance Criteria:**
  - App fails fast on invalid production config; logs never contain secret values.
- **Validation Commands:**
  - `pytest ai_video_studio/tests/test_config.py`
  - `pytest`
- **Completion Requirements:** Configuration validation tested.

---

### Task INFRA-02: Rate Limiting, CORS & Security Headers
- **Task ID:** `INFRA-02`
- **Phase:** Phase 8 — Production Infrastructure
- **Title:** Rate Limiting, CORS & Security Headers
- **Status:** `NOT_STARTED`
- **Objective:** Protect API endpoints from abuse, credential stuffing, and unauthorized cross-origin requests.
- **Context:** Public endpoints like `/api/auth/login` and `/api/projects` need strict rate limits.
- **Requirements:**
  1. IP-based and user-based rate limiting middleware (slowapi or redis-rate-limit).
  2. Strict CORS policy matching `DASHBOARD_CORS_ORIGINS`.
  3. Security headers (HSTS, CSP, X-Frame-Options, X-Content-Type-Options).
- **Implementation Guidance:**
  - Configure middleware in `ai_video_studio/web_api/__init__.py`.
- **Allowed files/directories:**
  - `ai_video_studio/web_api/__init__.py`
  - `ai_video_studio/web_api/middleware/**`
- **Dependencies:** `INFRA-01`
- **Acceptance Criteria:**
  - Exceeding login attempts triggers 429 Too Many Requests.
  - Security headers present on all HTTP responses.
- **Validation Commands:**
  - `pytest ai_video_studio/tests/web_api/test_security.py`
- **Completion Requirements:** Security middleware verified.

---

# Phase 9 — Scalability & High Availability

### Task SCALE-01: Multi-Replica API Deployment & Worker Autoscaling
- **Task ID:** `SCALE-01`
- **Phase:** Phase 9 — Scalability
- **Title:** Multi-Replica API Deployment & Worker Autoscaling
- **Status:** `NOT_STARTED`
- **Objective:** Enable horizontal scaling for the FastAPI web layer and independent autoscaling for render worker nodes.
- **Context:** Decoupling API from workers enables scaling the web dashboard to thousands of users while dedicated GPU/CPU workers handle rendering.
- **Requirements:**
  1. Remove `numReplicas: 1` restriction in `railway.json`.
  2. Add dedicated worker deployment specification (`Dockerfile.worker`, start command).
  3. Verify stateless request handling across multiple instances.
- **Implementation Guidance:**
  - Update `railway.json` and container specifications.
- **Allowed files/directories:**
  - `ai_video_studio/railway.json`
  - `ai_video_studio/Dockerfile*`
  - `ai_video_studio/DEPLOYMENT.md`
- **Dependencies:** `INFRA-02`
- **Acceptance Criteria:**
  - Multiple API instances share database and job queue without state discrepancies.
- **Validation Commands:**
  - `pytest`
- **Completion Requirements:** Deployment manifests verified.

---

# Phase 10 — Production Readiness & Release

### Task REL-01: End-to-End System Verification & Release Audit
- **Task ID:** `REL-01`
- **Phase:** Phase 10 — Production Readiness
- **Title:** End-to-End System Verification & Release Audit
- **Status:** `NOT_STARTED`
- **Objective:** Perform full end-to-end integration verification, security review, performance audit, and operator documentation.
- **Context:** Final quality gate before opening AI Video Studio to production creators.
- **Requirements:**
  1. Comprehensive E2E automated test: User registration -> project creation -> Director run -> media upload -> Producer run -> render compilation -> YouTube publish check.
  2. Security audit: verify zero credentials in codebase, proper secret rotation runbook.
  3. Load testing: simulate concurrent project renders.
  4. Publish updated architecture and operator runbooks.
- **Implementation Guidance:**
  - Add E2E tests under `ai_video_studio/tests/e2e/` and `frontend/e2e/`.
- **Allowed files/directories:**
  - `ai_video_studio/tests/e2e/**`
  - `frontend/e2e/**`
  - `DEPLOYMENT.md`
  - `README.md`
- **Dependencies:** `SCALE-01`
- **Acceptance Criteria:**
  - 100% of unit, integration, and E2E tests pass.
  - Zero critical vulnerabilities in dependency audit.
- **Validation Commands:**
  - `pytest`
  - `npm --prefix frontend run test`
  - `npm --prefix frontend run lint`
  - `npm --prefix frontend run build`
- **Completion Requirements:** Production sign-off complete.



# AI Video Studio — Master Implementation Plan

## 1. Project Objective

AI Video Studio is a production-oriented AI video creation and production platform.

The platform should allow users to:

* create an account
* authenticate securely
* create and manage video projects
* plan scenes
* manage assets
* generate AI video content
* process video through the production pipeline
* edit and assemble generated content
* manage subtitles
* manage music
* export final videos
* publish or prepare publishing metadata
* use the platform through a subscription/credit system
* scale reliably as the number of users increases

The implementation must preserve and extend the existing AI Video Studio architecture.

---

# 2. Execution Rules

This document is executed sequentially.

Only the first eligible incomplete task may be implemented.

The implementation agent must:

1. Read `AGENTS.md`.
2. Read this file.
3. Find the first eligible task.
4. Read the complete task specification.
5. Inspect the relevant existing implementation.
6. Implement the task.
7. Run validation.
8. Fix errors.
9. Verify acceptance criteria.
10. Mark the task `COMPLETED`.
11. Update the execution state.
12. Continue to the next eligible task.

Do not skip tasks.

Do not mark incomplete work as complete.

Do not begin a task whose dependencies are not complete.

---

# 3. Status Definitions

Allowed statuses:

* `NOT_STARTED`
* `IN_PROGRESS`
* `BLOCKED`
* `COMPLETED`

---

# 4. Global Engineering Requirements

All tasks must:

* preserve existing architecture
* reuse existing components
* avoid unnecessary dependencies
* avoid unrelated modifications
* maintain backward compatibility where practical
* include appropriate error handling
* include appropriate validation
* maintain security
* maintain responsive UX
* maintain performance
* avoid exposing secrets
* avoid trusting frontend state for security decisions

---

# 5. Existing Project First

Before implementing tasks, inspect the repository and identify:

* existing frontend
* existing backend
* existing database
* existing authentication
* existing AI pipeline
* existing video pipeline
* existing Producer Studio
* existing agents
* existing asset system
* existing timeline system
* existing subtitle system
* existing music system
* existing editing system
* existing publishing metadata system
* existing FFmpeg execution system
* existing tests
* existing deployment configuration

Do not assume that a listed feature is missing until the repository has been inspected.

If functionality already exists, extend or integrate it instead of rebuilding it.

---

# 6. Execution State

```text
Current Phase: 1
Current Task: TASK-001
Last Completed Task: None
Last Validation: Not started
Blocked Tasks: None
```

This section must always reflect the actual project state.

---

# Phase 1 — Authentication Experience

## TASK-001 — Login Page UI

Status: `NOT_STARTED`

### Objective

Create a polished, responsive, reliable login experience for AI Video Studio.

### Product Context

AI Video Studio is a professional AI video creation platform.

The login page should feel like a modern creative SaaS product rather than a generic authentication template.

### Design Goals

The login experience should be:

* premium
* cinematic
* minimal
* modern
* professional
* trustworthy
* responsive
* fast
* accessible
* smooth

Avoid:

* excessive gradients
* excessive glassmorphism
* unnecessary animations
* clutter
* generic template styling
* oversized UI elements

### Required UI

Include:

1. AI Video Studio branding
2. Product tagline
3. Google sign-in UI
4. Email input
5. Password input
6. Password visibility toggle
7. Forgot password link
8. Sign In button
9. Sign Up navigation
10. Loading state
11. Validation states
12. Error states
13. Responsive mobile layout

### Functional Requirements

At this stage:

* implement frontend UI only
* do not implement real authentication
* do not implement OAuth
* do not connect a database
* do not implement payment functionality
* do not modify unrelated backend functionality

Email validation must work.

Required fields must be validated.

Multiple submissions must be prevented while loading.

### UX Requirements

The page must include:

* keyboard navigation
* accessible labels
* visible focus states
* clear validation messages
* disabled/loading state during submission
* responsive layout
* sensible spacing
* consistent typography
* mobile usability

### Engineering Requirements

Before changing code:

1. Inspect the existing frontend.
2. Identify the existing routing system.
3. Identify existing UI components.
4. Identify existing styling conventions.
5. Reuse existing components wherever possible.

Do not introduce a new UI framework if an existing one is already used.

### Acceptance Criteria

* Login page renders successfully.
* Page is responsive.
* Email validation works.
* Password validation works.
* Password visibility toggle works.
* Loading state works.
* Sign-up navigation/placeholder works.
* Forgot-password UI works as a placeholder.
* Google login UI works as a placeholder.
* No console errors are introduced.
* Existing functionality remains intact.
* Existing tests/lint/type checks/build pass where applicable.

### Validation

Run the project's existing:

* lint
* type check
* tests
* build

as applicable.

### Completion Requirements

Only mark `TASK-001` as `COMPLETED` after all acceptance criteria pass.

---

# TASK-002 — Authentication Architecture

Status: `NOT_STARTED`

Dependencies:

```text
TASK-001
```

### Objective

Design and implement the real authentication system while preserving the existing project architecture.

### Requirements

Determine the appropriate authentication architecture based on the existing stack.

Support, where applicable:

* user registration
* login
* logout
* sessions
* protected routes
* password recovery
* secure password handling
* authentication state

### Security

Authentication must be enforced server-side.

Do not rely solely on frontend route protection.

### Acceptance Criteria

* Users can securely register.
* Users can securely log in.
* Users can log out.
* Protected resources reject unauthenticated requests.
* Sessions are handled securely.
* Passwords are never stored in plaintext.
* Relevant validation passes.

---

# TASK-003 — Signup Experience

Status: `NOT_STARTED`

Dependencies:

```text
TASK-002
```

### Objective

Create the production-quality signup experience.

### Requirements

Include:

* name where appropriate
* email
* password
* password confirmation where appropriate
* validation
* loading states
* error states
* success handling
* login navigation

### Acceptance Criteria

* Signup works with the authentication system.
* Validation works.
* Errors are clear.
* Mobile UX works.
* Security requirements are satisfied.

---

# TASK-004 — User Session and Protected Application

Status: `NOT_STARTED`

Dependencies:

```text
TASK-003
```

### Objective

Connect authentication to the main application.

### Requirements

Implement:

* authenticated session state
* protected application routes
* unauthenticated redirect
* authenticated navigation
* logout

---

# Phase 2 — Application Dashboard

## TASK-005 — Dashboard Foundation

Status: `NOT_STARTED`

Dependencies:

```text
TASK-004
```

### Objective

Create the authenticated AI Video Studio dashboard.

### Requirements

Dashboard should provide access to:

* projects
* create project
* recent projects
* account
* settings
* usage/subscription information

Preserve existing Producer Studio functionality.

---

# TASK-006 — Project Management

Status: `NOT_STARTED`

Dependencies:

```text
TASK-005
```

### Objective

Implement persistent user projects.

### Requirements

Users should be able to:

* create projects
* rename projects
* open projects
* delete projects where appropriate
* view project status
* access project history

Use the existing project architecture where available.

---

# Phase 3 — Subscription and Monetization

## TASK-007 — Pricing Architecture

Status: `NOT_STARTED`

Dependencies:

```text
TASK-006
```

### Objective

Design the subscription and entitlement system.

### Initial Concept

Potential plans:

```text
Free
Starter
Pro
Business
```

The exact pricing must be determined before production launch based on:

* infrastructure costs
* AI generation costs
* storage costs
* expected usage
* target customers
* margins

Do not hardcode pricing throughout the application.

Create a centralized plan/entitlement model.

---

# TASK-008 — Usage and Credit System

Status: `NOT_STARTED`

Dependencies:

```text
TASK-007
```

### Objective

Implement usage tracking and credit limits.

### Requirements

Track:

* user
* plan
* credits
* usage
* generation count
* relevant resource consumption

The backend must be authoritative.

Users must not be able to manipulate credits from the frontend.

---

# TASK-009 — Payment Gateway

Status: `NOT_STARTED`

Dependencies:

```text
TASK-008
```

### Objective

Integrate the appropriate payment gateway.

For an India-first launch, evaluate Razorpay.

For international payments, evaluate Stripe.

Do not hardcode payment credentials.

### Requirements

Implement:

* checkout
* payment creation
* server-side verification
* webhook handling
* successful payment
* failed payment
* duplicate webhook protection
* subscription state updates

---

# TASK-010 — Subscription Lifecycle

Status: `NOT_STARTED`

Dependencies:

```text
TASK-009
```

### Objective

Implement:

* activation
* renewal
* cancellation
* expiration
* failed renewal
* plan upgrade
* plan downgrade
* entitlement updates

All subscription state must be stored and verified server-side.

---

# Phase 4 — AI Video Production

## TASK-011 — Integrate Existing Producer Studio

Status: `NOT_STARTED`

Dependencies:

```text
TASK-010
```

### Objective

Connect authenticated users and projects to the existing Producer Studio pipeline.

Do not rewrite existing working functionality.

---

# TASK-012 — Asset Pipeline

Status: `NOT_STARTED`

Dependencies:

```text
TASK-011
```

### Objective

Ensure project assets are properly:

* validated
* stored
* referenced
* versioned where necessary
* accessible only to authorized users

---

# TASK-013 — Scene Generation Pipeline

Status: `NOT_STARTED`

Dependencies:

```text
TASK-012
```

### Objective

Integrate AI scene generation into the authenticated project workflow.

Reuse existing scene planning and generation systems.

---

# TASK-014 — Timeline and Editing Pipeline

Status: `NOT_STARTED`

Dependencies:

```text
TASK-013
```

### Objective

Integrate existing:

* timeline planning
* subtitle planning
* music planning
* editing planning
* FFmpeg execution

into the production workflow.

---

# TASK-015 — Publishing Metadata

Status: `NOT_STARTED`

Dependencies:

```text
TASK-014
```

### Objective

Complete publishing metadata generation and integrate it into the final production workflow.

---

# Phase 5 — Asynchronous Processing

## TASK-016 — Job System

Status: `NOT_STARTED`

Dependencies:

```text
TASK-015
```

### Objective

Move long-running AI/video operations into an asynchronous job architecture.

### Target Flow

```text
API Request
    ↓
Create Job
    ↓
Queue
    ↓
Worker
    ↓
AI / Video Processing
    ↓
Storage
    ↓
Update Job
    ↓
Client receives status
```

---

# TASK-017 — Worker Reliability

Status: `NOT_STARTED`

Dependencies:

```text
TASK-016
```

### Requirements

Implement:

* retries
* failure states
* job timeouts
* idempotency where required
* structured logging
* job progress where practical

---

# Phase 6 — Storage

## TASK-018 — Object Storage

Status: `NOT_STARTED`

Dependencies:

```text
TASK-017
```

### Objective

Move generated media and large assets to appropriate object storage.

Evaluate:

* AWS S3
* Cloudflare R2
* equivalent production storage

The choice must be compatible with the existing architecture and economics.

---

# Phase 7 — Reliability and Security

## TASK-019 — Rate Limiting

Status: `NOT_STARTED`

Dependencies:

```text
TASK-018
```

### Objective

Protect APIs and expensive AI operations from abuse.

Implement appropriate limits based on:

* endpoint
* authentication status
* subscription
* resource cost

---

# TASK-020 — Caching

Status: `NOT_STARTED`

Dependencies:

```text
TASK-019
```

### Objective

Identify high-value caching opportunities.

Evaluate Redis or equivalent infrastructure where justified.

Do not cache sensitive data incorrectly.

---

# TASK-021 — Error Handling and Observability

Status: `NOT_STARTED`

Dependencies:

```text
TASK-020
```

### Objective

Implement production-quality:

* structured logging
* error tracking
* metrics
* health checks
* job monitoring
* API monitoring

---

# Phase 8 — Scalability

## TASK-022 — Database Optimization

Status: `NOT_STARTED`

Dependencies:

```text
TASK-021
```

### Objective

Optimize database performance.

Evaluate:

* indexes
* query patterns
* connection pooling
* pagination
* caching
* slow queries

Do not prematurely introduce sharding.

---

# TASK-023 — Horizontal API Scaling

Status: `NOT_STARTED`

Dependencies:

```text
TASK-022
```

### Objective

Ensure the API can run multiple instances behind a load balancer.

The API should remain stateless wherever practical.

---

# TASK-024 — Worker Scaling

Status: `NOT_STARTED`

Dependencies:

```text
TASK-023
```

### Objective

Allow AI/video workers to scale independently from API servers.

---

# TASK-025 — CDN

Status: `NOT_STARTED`

Dependencies:

```text
TASK-024
```

### Objective

Deliver static assets and appropriate media efficiently through a CDN.

---

# TASK-026 — Autoscaling

Status: `NOT_STARTED`

Dependencies:

```text
TASK-025
```

### Objective

Implement automatic infrastructure scaling based on meaningful workload metrics.

Do not add Kubernetes or other complex orchestration unless the actual workload justifies it.

---

# Phase 9 — Production Readiness

## TASK-027 — Security Review

Status: `NOT_STARTED`

Dependencies:

```text
TASK-026
```

Review:

* authentication
* authorization
* secrets
* API security
* payment security
* file access
* rate limiting
* input validation
* dependency vulnerabilities

---

# TASK-028 — Performance Testing

Status: `NOT_STARTED`

Dependencies:

```text
TASK-027
```

Evaluate:

* API latency
* concurrent users
* database performance
* queue throughput
* worker throughput
* media processing
* frontend performance

---

# TASK-029 — Backup and Recovery

Status: `NOT_STARTED`

Dependencies:

```text
TASK-028
```

Implement and verify:

* database backups
* storage durability strategy
* recovery procedures
* failure handling

---

# TASK-030 — Production Deployment

Status: `NOT_STARTED`

Dependencies:

```text
TASK-029
```

Deploy the application using the architecture selected during implementation.

Verify:

* production configuration
* environment variables
* monitoring
* health checks
* rollback strategy
* security
* performance

---

# TASK-031 — Final Production Audit

Status: `NOT_STARTED`

Dependencies:

```text
TASK-030
```

Perform a complete system audit.

Verify:

* functionality
* authentication
* authorization
* payments
* subscriptions
* credits
* AI generation
* queues
* workers
* storage
* monitoring
* security
* scalability
* documentation

Only mark the project production-ready after the complete audit passes.

---

# 7. Task Execution Record

After each task is completed, maintain a concise record here.

Example:

```text
TASK-001
Status: COMPLETED
Date:
Summary:
Validation:
Notes:
```

Do not fabricate completion records.

---

# 8. Future Work

When new requirements are discovered that are outside the current task:

1. Do not silently expand the current task.
2. Add the requirement to this section.
3. Convert it into a formal task when appropriate.

---

# 9. Final Execution Principle

The project must evolve through controlled incremental implementation.

The implementation agent should continuously follow:

```text
READ
 ↓
INSPECT
 ↓
IMPLEMENT
 ↓
VALIDATE
 ↓
FIX
 ↓
VERIFY
 ↓
UPDATE PLAN
 ↓
NEXT TASK
```

Never skip validation.

Never skip dependencies.

Never mark incomplete work as complete.


