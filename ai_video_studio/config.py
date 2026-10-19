import os
import warnings
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


def _parse_bool_env(name: str) -> Optional[bool]:
    """True/False if `name` is set to a recognizable truthy/falsy string, or
    None if unset/blank - lets a setting distinguish "explicitly configured"
    from "fall back to the environment-appropriate default" (see
    resolve_cookie_secure/resolve_cookie_samesite below)."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None
    return raw.strip().lower() in ("1", "true", "yes", "on")


def resolve_cookie_secure(environment: str, override: Optional[bool]) -> bool:
    """LOCAL (development) defaults to COOKIE_SECURE=false; STAGING/
    PRODUCTION default to true - an explicit COOKIE_SECURE env var
    (`override`, already parsed by _parse_bool_env) always wins. Pure
    function so tests/test_config_cookies.py can exercise every
    (environment, override) combination directly, without needing to
    reload config.py or touch process env vars."""
    if override is not None:
        return override
    return environment in ("staging", "production")


def resolve_cookie_samesite(environment: str, override: Optional[str]) -> str:
    """LOCAL (development) defaults to SameSite=Lax (frontend and API are
    same-site in dev). STAGING/PRODUCTION default to SameSite=None, because
    that split puts the Next.js frontend (Vercel) and this API (Railway) on
    different sites, which needs a credentialed cross-site cookie - only
    honored by browsers alongside Secure=true (enforced by
    validate_cookie_config, not here). An explicit COOKIE_SAMESITE env var
    (`override`) always wins, e.g. for a same-site staging/prod deployment
    that doesn't need SameSite=None."""
    if override:
        return override
    return "none" if environment in ("staging", "production") else "lax"


def validate_cookie_config(environment: str, cookie_secure: bool, cookie_samesite: str) -> None:
    """Fails fast (raises) on a session-cookie configuration that would ship
    an insecure or browser-invalid cookie. Called once at import time below
    against the real process env, and exercised directly by
    tests/test_config_cookies.py against arbitrary combinations - kept as a
    standalone function specifically so tests don't need a fresh process/
    import per case to exercise it."""
    if cookie_samesite not in ("lax", "strict", "none"):
        raise RuntimeError(
            f"COOKIE_SAMESITE must be one of 'lax', 'strict', or 'none' (got {cookie_samesite!r})."
        )

    if environment in ("staging", "production") and not cookie_secure:
        raise RuntimeError(
            "Refusing to start with COOKIE_SECURE=false while ENVIRONMENT="
            f"{environment!r}. Session cookies must be Secure in a deployed "
            "environment - set COOKIE_SECURE=true, or leave COOKIE_SECURE "
            "unset entirely to use the environment-appropriate default."
        )

    if cookie_samesite == "none" and not cookie_secure:
        # Browsers reject/drop a SameSite=None cookie unless it also carries
        # Secure - this holds regardless of ENVIRONMENT, so it's checked
        # independently of the staging/production rule above.
        raise RuntimeError(
            "COOKIE_SAMESITE=none requires COOKIE_SECURE=true - browsers "
            "reject non-secure SameSite=None cookies."
        )


class Settings:
    GEMINI_API_KEYS: list = [k.strip() for k in (os.getenv("GEMINI_API_KEYS") or os.getenv("GEMINI_API_KEY", "")).split(",") if k.strip()]
    GEMINI_API_KEY: str = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else ""
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    OPENAI_API_KEYS: list = [k.strip() for k in (os.getenv("OPENAI_API_KEYS") or os.getenv("OPENAI_API_KEY", "")).split(",") if k.strip()]
    OPENAI_API_KEY: str = OPENAI_API_KEYS[0] if OPENAI_API_KEYS else ""
    GPT_MODEL: str = os.getenv("GPT_MODEL", "gpt-4o-mini")

    GROQ_API_KEYS: list = [k.strip() for k in (os.getenv("GROQ_API_KEYS") or os.getenv("GROQ_API_KEY", "")).split(",") if k.strip()]
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    CEREBRAS_API_KEYS: list = [k.strip() for k in (os.getenv("CEREBRAS_API_KEYS") or os.getenv("CEREBRAS_API_KEY", "")).split(",") if k.strip()]
    CEREBRAS_API_KEY: str = CEREBRAS_API_KEYS[0] if CEREBRAS_API_KEYS else ""
    CEREBRAS_MODEL: str = os.getenv("CEREBRAS_MODEL", "gpt-oss-120b")

    OPENROUTER_API_KEYS: list = [k.strip() for k in (os.getenv("OPENROUTER_API_KEYS") or os.getenv("OPENROUTER_API_KEY", "")).split(",") if k.strip()]
    OPENROUTER_API_KEY: str = OPENROUTER_API_KEYS[0] if OPENROUTER_API_KEYS else ""
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash")
    OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

    # Order of providers to attempt in FailoverLLMClient
    LLM_PROVIDER_ORDER: list = [
        p.strip().lower()
        for p in os.getenv(
            "LLM_PROVIDER_ORDER",
            "openrouter,gemini,groq,cerebras,openai"
            if (os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENROUTER_API_KEYS"))
            else "groq,cerebras,openrouter,gemini,openai",
        ).split(",")
        if p.strip()
    ]

    # Google Veo (video_generation_engine/providers/google_veo.py) uses the
    # same Google AI Studio account as Gemini - GOOGLE_VEO_API_KEY lets a
    # deployment use a distinct/billing-separated key, but falls back to
    # GEMINI_API_KEY (already required for image generation) so a single key
    # is enough for both by default.
    GOOGLE_VEO_API_KEY: str = os.getenv("GOOGLE_VEO_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
    GOOGLE_VEO_MODEL: str = os.getenv("GOOGLE_VEO_MODEL", "veo-3.1-fast-generate-preview")

    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Overridable so a deployment with a mounted persistent volume (e.g.
    # Railway) can point this at the volume's mount path via env var;
    # defaults to the existing local-relative behavior unchanged.
    OUTPUT_DIR: Path = Path(os.getenv("OUTPUT_DIR", str(BASE_DIR / "outputs")))

    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.8"))
    LLM_MAX_OUTPUT_TOKENS: int = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "4096"))

    # Bounds for Director Studio's custom scene count override (New Project ->
    # Custom Scene Count). Env-overridable so a deployment can widen/narrow
    # the allowed range without a code change.
    MIN_SCENE_COUNT: int = int(os.getenv("MIN_SCENE_COUNT", "1"))
    MAX_SCENE_COUNT: int = int(os.getenv("MAX_SCENE_COUNT", "100"))

    # --- Phase 1.1 P0 fix: bounded pipeline concurrency (docs/phase1.1-p0-fixes.md) ---
    # Caps how many Director/Producer/Render/Publish runs may actually be
    # EXECUTING at once, on a dedicated thread pool separate from the one
    # Starlette uses for sync HTTP routes and BackgroundTasks dispatch
    # (see docs/phase1-stability-audit.md finding C1 - that shared 40-slot
    # anyio pool is what starved /health under load; this cap is
    # deliberately its own, smaller number, not derived from or tied to
    # that 40). Conservative default for today's single-uvicorn-worker,
    # single-container deployment (railway.json: numReplicas 1): each slot
    # is CPU/LLM/ffmpeg-bound work sharing the one process with the API
    # itself, so a small cap leaves the process real headroom to keep
    # answering ordinary requests (and the health check) even while every
    # pipeline slot is busy.
    PIPELINE_MAX_CONCURRENCY: int = int(os.getenv("PIPELINE_MAX_CONCURRENCY", "4"))

    # Anonymous project access (docs/authentication.md). Off by default:
    # POST /projects (which starts a paid, LLM-backed Director run) and
    # GET /projects require a signed-in user. Set true to restore the
    # earlier documented legacy mode, where anonymous callers may create
    # ownerless projects and list ownerless projects (never owned ones).
    # Access to an existing ownerless project by id is unaffected either way.
    ALLOW_ANONYMOUS_PROJECTS: bool = bool(_parse_bool_env("ALLOW_ANONYMOUS_PROJECTS"))

    # Hard wall-clock ceiling for one pipeline run, independent of (and in
    # addition to) each stage's own internal timeouts (LLM clients: 60s x 3
    # retries per call; ffmpeg: RenderOptions.timeout_seconds, enforced as a
    # real subprocess kill). Sized generously above the audit's own
    # worst-case estimate for a legitimate MAX_SCENE_COUNT=100 Director run
    # (~30-35 minutes in the happy path: ~100-200 sequential per-shot LLM
    # calls) so this is a backstop against a genuinely stuck run, not a
    # tool for capping normal heavy usage - Fix 1's concurrency cap is what
    # actually protects the API under load. Raise this (or lower
    # MAX_SCENE_COUNT) if real measurements show typical heavy runs
    # exceeding it.
    PIPELINE_TIMEOUT_SECONDS: float = float(os.getenv("PIPELINE_TIMEOUT_SECONDS", "1800"))

    # --- AWS deployment prerequisites (docs/aws-production-architecture.md) ---
    # All optional/blank by default so local dev, the CLIs, and the entire
    # existing test suite are completely unaffected - each subsystem below
    # only activates when its own env vars are actually set (see
    # storage/s3_syncing_project_manager.py, db/, web_api/dependencies.py).

    AWS_REGION: str = os.getenv("AWS_REGION", "")

    # Prerequisite 1: S3-backed project storage (storage/s3_project_sync.py).
    # Blank means "local disk only" - today's exact behavior.
    S3_BUCKET_NAME: str = os.getenv("S3_BUCKET_NAME", "")

    # Prerequisite 2: RDS-backed user store and run registry (db/). Blank
    # DB_HOST means "local file store / in-memory registry" - today's exact
    # behavior (web_api/dependencies.py::get_user_store,
    # web_api/__init__.py::create_app's RunRegistry construction).
    DB_HOST: str = os.getenv("DB_HOST", "")
    DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
    DB_NAME: str = os.getenv("DB_NAME", "")
    DB_USER: str = os.getenv("DB_USER", "")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")

    # Prerequisite 3: SQS-based worker dispatch (worker.py,
    # web_api/pipeline_dispatch.py). Blank means "dispatch in-process via
    # PipelineExecutor" - today's exact behavior (Phase 1.1 P0 fix).
    SQS_QUEUE_URL: str = os.getenv("SQS_QUEUE_URL", "")

    # Prerequisite 4: SES-backed password-reset email (auth/email.py,
    # web_api/routers/auth.py's forgot_password). Blank SES_FROM_EMAIL means
    # "no email delivery configured" - forgot-password falls back to its
    # existing dev-mode-only reset_token response field (never sent in
    # production either way - see auth/email.py's docstring). No AWS access
    # keys are read or accepted here: boto3's default credential chain
    # resolves to the ECS task role in a deployed environment, or whatever
    # the operator's own AWS CLI/SSO session provides locally.
    SES_REGION: str = os.getenv("SES_REGION", "")
    SES_FROM_EMAIL: str = os.getenv("SES_FROM_EMAIL", "")

    # Absolute origin of the deployed frontend, used only to build the
    # clickable link inside the password-reset email (an email client has
    # no origin of its own to resolve a relative /reset-password path
    # against). Blank locally - see auth/email.py for the fallback when this
    # is unset but SES_FROM_EMAIL is (email is sent with a relative-path
    # link rather than silently failing).
    FRONTEND_BASE_URL: str = os.getenv("FRONTEND_BASE_URL", "").rstrip("/")

    # --- Session cookie security (the access_token cookie web_api/routers/
    # auth.py's register/login/logout set) ---
    # "development" (local, the CLIs, and the whole test suite unless a test
    # overrides it) / "staging" / "production" - the one flag every other
    # cookie default below is computed from.
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development").strip().lower()

    # Secure/SameSite must differ by deployment shape: local dev is plain
    # HTTP on one origin (Secure=True would make the browser silently drop
    # the cookie; SameSite=Lax is enough since frontend/API are same-site in
    # dev too), while staging/production put the Next.js frontend (Vercel)
    # and this API (Railway) on different sites, which needs a credentialed
    # cross-site cookie - SameSite=None, which browsers only honor alongside
    # Secure=True. Both are explicitly overridable (COOKIE_SECURE/
    # COOKIE_SAMESITE env vars) for a same-site staging/prod deployment that
    # doesn't need the cross-site case, but validate_cookie_config below
    # refuses to let ENVIRONMENT=staging/production ever resolve to an
    # insecure cookie even if COOKIE_SECURE is explicitly set wrong. See
    # resolve_cookie_secure/resolve_cookie_samesite above for the (pure,
    # directly-tested) resolution logic itself.
    COOKIE_SECURE: bool = resolve_cookie_secure(ENVIRONMENT, _parse_bool_env("COOKIE_SECURE"))
    COOKIE_SAMESITE: str = resolve_cookie_samesite(ENVIRONMENT, os.getenv("COOKIE_SAMESITE", "").strip().lower() or None)


settings = Settings()
settings.OUTPUT_DIR.mkdir(exist_ok=True)

validate_cookie_config(settings.ENVIRONMENT, settings.COOKIE_SECURE, settings.COOKIE_SAMESITE)

has_any_llm_key = bool(
    settings.OPENROUTER_API_KEYS
    or settings.GEMINI_API_KEYS
    or settings.OPENAI_API_KEYS
    or settings.GROQ_API_KEYS
    or settings.CEREBRAS_API_KEYS
)

if not has_any_llm_key:
    warnings.warn(
        "No LLM API keys configured. Set at least one of OPENROUTER_API_KEY, "
        "GEMINI_API_KEY, OPENAI_API_KEY, GROQ_API_KEY, or CEREBRAS_API_KEY in .env"
    )
