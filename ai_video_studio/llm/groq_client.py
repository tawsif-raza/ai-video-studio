import itertools
from openai import OpenAI

from agents.base.exceptions import LLMCallError
from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class GroqClient:
    """
    Groq's free tier requires no credit card and no billing setup, unlike OpenAI.
    Its API is OpenAI-compatible, so this reuses the `openai` package we already
    have installed - just pointed at Groq's base_url instead of OpenAI's.

    Supports multiple API keys with automatic rotation on rate-limit or auth errors.
    Matches GeminiClient/GPTClient's .generate() signature exactly, so it's a
    drop-in replacement anywhere GPTClient was used.
    """

    _key_cycle = None

    def __init__(self, model_name: str = None, api_key: str = None):
        self.model_name = model_name or settings.GROQ_MODEL
        self._api_keys = settings.GROQ_API_KEYS

        if api_key:
            self._api_keys = [api_key]

        if not self._api_keys:
            raise ValueError("No Groq API keys configured. Set GROQ_API_KEYS in .env")

        self._key_cycle = itertools.cycle(self._api_keys)
        self._client = OpenAI(api_key=self._next_key(), base_url=GROQ_BASE_URL)

    def _next_key(self) -> str:
        return next(self._key_cycle)

    def _rotate_key(self):
        new_key = self._next_key()
        self._client = OpenAI(api_key=new_key, base_url=GROQ_BASE_URL)
        logger.info("Rotated to next Groq API key")

    def generate(
        self,
        prompt: str,
        system_instruction: str = None,
        temperature: float = None,
        json_mode: bool = True,
    ) -> str:
        last_error = None

        for attempt in range(len(self._api_keys)):
            try:
                messages = []
                if system_instruction:
                    messages.append({"role": "system", "content": system_instruction})
                messages.append({"role": "user", "content": prompt})

                response = self._client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
                    max_tokens=settings.LLM_MAX_OUTPUT_TOKENS,
                    response_format={"type": "json_object"} if json_mode else {"type": "text"},
                )
                text = response.choices[0].message.content
                if not text:
                    raise LLMCallError("Groq returned an empty response")
                return text

            except LLMCallError as e:
                last_error = e
                logger.warning(f"Groq attempt {attempt + 1} call error: {e}")
                if len(self._api_keys) > 1 and attempt < len(self._api_keys) - 1:
                    self._rotate_key()
                    continue
                raise
            except Exception as e:
                last_error = e
                if len(self._api_keys) > 1 and attempt < len(self._api_keys) - 1:
                    logger.warning(f"Groq attempt {attempt + 1} failed ({e}). Rotating key...")
                    self._rotate_key()
                    continue

                logger.error(f"Groq call failed: {e}")
                raise LLMCallError(str(e)) from e

        raise LLMCallError(f"All Groq API keys exhausted. Last error: {last_error}")