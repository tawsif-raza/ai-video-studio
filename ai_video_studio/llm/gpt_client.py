from openai import OpenAI

from agents.base.exceptions import LLMCallError
from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class GPTClient:
    """
    Thin wrapper around the OpenAI API. Deliberately matches GeminiClient's
    .generate() signature exactly, so any agent can be pointed at either client
    without changing a line of the agent itself:

        prompt_agent = PromptGeneratorAgent(GPTClient())
        image_agent  = ImageGenerationAgent(GeminiClient())

    BaseAgent only ever calls self.llm.generate(...) — it has no idea which
    provider is behind it.
    """

    def __init__(self, model_name: str = None, api_key: str = None):
        self.model_name = model_name or settings.GPT_MODEL
        self._client = OpenAI(api_key=api_key or settings.OPENAI_API_KEY)

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
                raise LLMCallError("GPT returned an empty response")
            return text

        except LLMCallError:
            raise
        except Exception as e:
            logger.error(f"GPT call failed: {e}")
            raise LLMCallError(str(e)) from e