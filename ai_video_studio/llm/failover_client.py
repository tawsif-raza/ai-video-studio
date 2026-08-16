from agents.base.exceptions import LLMCallError
from config import settings
from llm.cerebras_client import CerebrasClient
from llm.gemini_client import GeminiClient
from llm.gpt_client import GPTClient
from llm.groq_client import GroqClient
from utils.logger import get_logger

logger = get_logger(__name__)

# Superset of the markers groq_client.py already treats as "try a different
# key" rather than a hard failure - any key/quota/billing problem, not a
# real generation error. Includes payment/quota markers (e.g. Cerebras'
# "402 payment_required" when an account has no credit) that groq_client.py
# doesn't need to check itself since Groq's free tier has no billing state.
KEY_ISSUE_MARKERS = ("rate_limit", "429", "auth", "401", "quota", "402", "payment", "insufficient")

# Ordered by preference: Groq (free tier, and itself rotates across multiple
# keys - see GroqClient) first, then Cerebras as the fallback the user added
# a key for, then the paid Gemini/OpenAI providers last.
_PROVIDERS = (
    ("Groq", GroqClient, "GROQ_API_KEYS"),
    ("Cerebras", CerebrasClient, "CEREBRAS_API_KEY"),
    ("Gemini", GeminiClient, "GEMINI_API_KEY"),
    ("OpenAI", GPTClient, "OPENAI_API_KEY"),
)


class FailoverLLMClient:
    """
    Tries each configured LLM provider in turn - Groq, then Cerebras, then
    Gemini, then OpenAI - falling through to the next one whenever the
    current provider reports a rate-limit/auth/quota issue. Matches
    GeminiClient/GPTClient/GroqClient's .generate() signature exactly, so
    it's a drop-in replacement anywhere those were used (app.py,
    web_api/dependencies.py).

    Providers without a configured API key are skipped entirely. GroqClient
    already rotates across multiple keys internally before raising, so this
    class only needs to react to the exhausted/failed provider as a whole.
    """

    def __init__(self):
        self._providers = []
        for name, client_cls, settings_attr in _PROVIDERS:
            if not getattr(settings, settings_attr):
                logger.info(f"{name} not configured (missing {settings_attr}), skipping in failover chain")
                continue
            self._providers.append((name, client_cls()))

        if not self._providers:
            raise ValueError(
                "No LLM providers configured. Set at least one of GROQ_API_KEY, "
                "CEREBRAS_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY in .env"
            )

    def generate(
        self,
        prompt: str,
        system_instruction: str = None,
        temperature: float = None,
        json_mode: bool = True,
    ) -> str:
        last_error = None

        for name, client in self._providers:
            try:
                return client.generate(prompt, system_instruction, temperature, json_mode)
            except LLMCallError as e:
                last_error = e
                error_msg = str(e).lower()

                if any(marker in error_msg for marker in KEY_ISSUE_MARKERS):
                    logger.warning(f"{name} unavailable ({e}), falling back to next provider")
                    continue

                logger.error(f"{name} call failed with a non-key error: {e}")
                raise

        raise LLMCallError(f"All LLM providers exhausted. Last error: {last_error}")
