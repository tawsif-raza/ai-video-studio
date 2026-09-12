from agents.base.exceptions import LLMCallError
from config import settings
from llm.cerebras_client import CerebrasClient
from llm.gemini_client import GeminiClient
from llm.gpt_client import GPTClient
from llm.groq_client import GroqClient
from llm.openrouter_client import OpenRouterClient
from utils.logger import get_logger

logger = get_logger(__name__)

# Markers that indicate quota, rate-limit, auth, billing, credit or transient issues
KEY_ISSUE_MARKERS = (
    "rate_limit",
    "429",
    "auth",
    "401",
    "403",
    "forbidden",
    "unauthorized",
    "quota",
    "402",
    "payment",
    "credit",
    "balance",
    "insufficient",
    "limit",
    "exhausted",
    "exceeded",
    "capacity",
    "overloaded",
    "unavailable",
    "500",
    "502",
    "503",
    "504",
    "timeout",
    "timed out",
    "connection",
)

_PROVIDER_REGISTRY = {
    "openrouter": ("OpenRouter", OpenRouterClient, "OPENROUTER_API_KEYS"),
    "gemini": ("Gemini", GeminiClient, "GEMINI_API_KEYS"),
    "groq": ("Groq", GroqClient, "GROQ_API_KEYS"),
    "cerebras": ("Cerebras", CerebrasClient, "CEREBRAS_API_KEYS"),
    "openai": ("OpenAI", GPTClient, "OPENAI_API_KEYS"),
}

_PROVIDERS = tuple(_PROVIDER_REGISTRY.values())


class FailoverLLMClient:
    """
    Tries each configured LLM provider in turn - e.g. OpenRouter, Gemini,
    Groq, Cerebras, OpenAI - falling through to the next provider whenever the
    current provider encounters any failure (rate-limit, credit/quota exhaustion,
    401/402/403/429/503, connection/timeout, empty response, or transient errors).

    Matches GeminiClient/GPTClient/GroqClient/OpenRouterClient's .generate()
    signature exactly, so it's a seamless drop-in replacement everywhere in the
    studio.
    """

    def __init__(self, provider_order: list = None):
        order = provider_order or settings.LLM_PROVIDER_ORDER
        self._providers = []

        seen = set()
        for key in order:
            norm_key = str(key).lower().strip()
            if norm_key in seen:
                continue
            seen.add(norm_key)

            if norm_key not in _PROVIDER_REGISTRY:
                logger.warning(f"Unknown LLM provider '{norm_key}' in LLM_PROVIDER_ORDER; skipping")
                continue

            name, client_cls, settings_attr = _PROVIDER_REGISTRY[norm_key]
            keys = getattr(settings, settings_attr, [])
            if not keys:
                logger.info(f"{name} not configured (missing {settings_attr}), skipping in failover chain")
                continue

            try:
                self._providers.append((name, client_cls()))
            except Exception as e:
                logger.warning(f"Failed to initialize provider {name} ({e}), skipping in failover chain")

        if not self._providers:
            raise ValueError(
                "No LLM providers configured. Set at least one of OPENROUTER_API_KEY, "
                "GEMINI_API_KEY, GROQ_API_KEY, CEREBRAS_API_KEY, or OPENAI_API_KEY in .env"
            )

        self._last_provider_name = None
        self._last_model_used = None

    @property
    def model_name(self) -> str:
        return self._last_model_used or "failover"

    def generate(
        self,
        prompt: str,
        system_instruction: str = None,
        temperature: float = None,
        json_mode: bool = True,
    ) -> str:
        errors = []

        for name, client in self._providers:
            try:
                result = client.generate(prompt, system_instruction, temperature, json_mode)
                self._last_provider_name = name
                self._last_model_used = getattr(client, "model_name", name)
                logger.info(f"LLM call succeeded using provider: {name} (model: {self._last_model_used})")
                return result
            except Exception as e:
                errors.append(f"{name}: {e}")
                logger.warning(
                    f"LLM provider '{name}' failed ({type(e).__name__}: {e}). "
                    f"Automatically switching to next provider in failover chain..."
                )
                continue

        joined_errors = "; ".join(errors)
        logger.error(f"All LLM providers exhausted. Errors: {joined_errors}")
        raise LLMCallError(f"All LLM providers exhausted. Errors: {joined_errors}")
