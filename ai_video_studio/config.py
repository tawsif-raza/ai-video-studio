import os
import warnings
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


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


settings = Settings()
settings.OUTPUT_DIR.mkdir(exist_ok=True)

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
