import itertools
from openai import OpenAI

from agents.base.exceptions import LLMCallError
from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class OpenRouterClient:
    """
    OpenRouter API client supporting unified access to top LLM models (Gemini,
    Claude, Llama, DeepSeek, etc.) via OpenAI-compatible endpoints.

    Supports multiple API keys with automatic rotation on rate-limit, auth,
    quota, credit exhaustion, or transient server errors.
    Matches GeminiClient/GPTClient/GroqClient's .generate() signature exactly,
    serving as a drop-in provider for FailoverLLMClient.
    """

    _key_cycle = None

    def __init__(self, model_name: str = None, api_key: str = None):
        self.model_name = model_name or settings.OPENROUTER_MODEL
        self._api_keys = [api_key] if api_key else list(settings.OPENROUTER_API_KEYS)

        if not self._api_keys:
            raise ValueError(
                "No OpenRouter API keys configured. Set OPENROUTER_API_KEY (or OPENROUTER_API_KEYS) in .env"
            )

        self._key_cycle = itertools.cycle(self._api_keys)
        self._current_key = self._next_key()
        self._client = self._create_client(self._current_key)

    def _next_key(self) -> str:
        return next(self._key_cycle)

    def _create_client(self, key: str) -> OpenAI:
        return OpenAI(
            api_key=key,
            base_url=settings.OPENROUTER_BASE_URL,
            default_headers={
                "HTTP-Referer": "https://ai-video-studio.local",
                "X-Title": "AI Video Studio",
            },
        )

    def _rotate_key(self):
        self._current_key = self._next_key()
        self._client = self._create_client(self._current_key)
        logger.info("Rotated to next OpenRouter API key")

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

                params = {
                    "model": self.model_name,
                    "messages": messages,
                    "temperature": temperature if temperature is not None else settings.LLM_TEMPERATURE,
                    "max_tokens": settings.LLM_MAX_OUTPUT_TOKENS,
                }
                if json_mode:
                    params["response_format"] = {"type": "json_object"}

                response = self._client.chat.completions.create(**params)
                text = response.choices[0].message.content
                if not text:
                    raise LLMCallError("OpenRouter returned an empty response")
                return text

            except LLMCallError as e:
                last_error = e
                logger.warning(f"OpenRouter attempt {attempt + 1} call error: {e}")
                if len(self._api_keys) > 1 and attempt < len(self._api_keys) - 1:
                    self._rotate_key()
                    continue
                raise
            except Exception as e:
                last_error = e
                # Rotate key if multiple keys exist
                if len(self._api_keys) > 1 and attempt < len(self._api_keys) - 1:
                    logger.warning(f"OpenRouter attempt {attempt + 1} failed ({e}). Rotating key...")
                    self._rotate_key()
                    continue

                logger.error(f"OpenRouter call failed: {e}")
                raise LLMCallError(str(e)) from e

        raise LLMCallError(f"All OpenRouter API keys exhausted. Last error: {last_error}")
