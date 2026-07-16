from google import genai
from google.genai import types

from agents.base.exceptions import LLMCallError
from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class GeminiClient:
    def __init__(self, model_name: str = None, api_key: str = None):
        self.model_name = model_name or settings.GEMINI_MODEL
        self._client = genai.Client(api_key=api_key or settings.GEMINI_API_KEY)

    def generate(self, prompt: str, system_instruction: str = None,
                 temperature: float = None, json_mode: bool = True) -> str:
        try:
            config = types.GenerateContentConfig(
                temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
                max_output_tokens=settings.LLM_MAX_OUTPUT_TOKENS,
                system_instruction=system_instruction,
                response_mime_type="application/json" if json_mode else "text/plain",
            )
            response = self._client.models.generate_content(
                model=self.model_name, contents=prompt, config=config
            )
            if not response or not response.text:
                raise LLMCallError("Gemini returned an empty response")
            return response.text
        except LLMCallError:
            raise
        except Exception as e:
            logger.error(f"Gemini call failed: {e}")
            raise LLMCallError(str(e)) from e