import os
import warnings
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


class Settings:
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    GPT_MODEL: str = os.getenv("GPT_MODEL", "gpt-4o-mini")

    GROQ_API_KEYS: list = [k.strip() for k in os.getenv("GROQ_API_KEYS", "").split(",") if k.strip()]
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    OUTPUT_DIR: Path = BASE_DIR / "outputs"

    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.8"))
    LLM_MAX_OUTPUT_TOKENS: int = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "4096"))


settings = Settings()
settings.OUTPUT_DIR.mkdir(exist_ok=True)

if not settings.GEMINI_API_KEY:
    warnings.warn(
        "GEMINI_API_KEY not set - Gemini-backed agents will fail until you set it in .env"
    )

if not settings.OPENAI_API_KEY:
    warnings.warn(
        "OPENAI_API_KEY not set - GPT-backed agents (e.g. Prompt Generator) will fail until you set it in .env"
    )

if not settings.GROQ_API_KEYS:
    warnings.warn(
        "GROQ_API_KEYS not set - Groq-backed agents will fail until you set it in .env"
    )
