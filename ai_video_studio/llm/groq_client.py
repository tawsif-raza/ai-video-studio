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

    Matches GeminiClient/GPTClient's .generate() signature exactly, so it's a
    drop-in replacement anywhere GPTClient was used.
    """

    def __init__(self, model_name: str = None, api_key: str = None):
        self.model_name = model_name or settings.GROQ_MODEL
        self._client = OpenAI(api_key=api_key or settings.GROQ_API_KEY, base_url=GROQ_BASE_URL)

    def generate(
        self,
        prompt: str,
        system_instruction: str = None,
        temperature: float = None,
        json_mode: bool = True,
    ) -> str:
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

        except LLMCallError:
            raise
        except Exception as e:
            logger.error(f"Groq call failed: {e}")
            raise LLMCallError(str(e)) from e