from google import genai
from google.genai import types

from agents.base.exceptions import LLMCallError
from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class GeminiImageClient:
    """
    Wraps Gemini's image generation (Nano Banana / gemini-2.5-flash-image).
    Unlike GeminiClient/GPTClient/GroqClient, this does NOT return text - it
    returns raw image bytes, because there's no JSON schema to validate an
    image against.
    """

    def __init__(self, model_name: str = None, api_key: str = None):
        self.model_name = model_name or "gemini-2.5-flash-image"
        self._client = genai.Client(api_key=api_key or settings.GEMINI_API_KEY)

    def generate_image(self, prompt: str) -> bytes:
        try:
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(response_modalities=["Text", "Image"]),
            )

            for part in response.candidates[0].content.parts:
                if part.inline_data is not None:
                    return part.inline_data.data

            raise LLMCallError("Gemini image response contained no image data")

        except LLMCallError:
            raise
        except Exception as e:
            logger.error(f"Gemini image generation failed: {e}")
            raise LLMCallError(str(e)) from e