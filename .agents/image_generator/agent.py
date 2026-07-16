from pathlib import Path

from tenacity import retry, stop_after_attempt, retry_if_exception_type, wait_exponential

from agents.base.exceptions import ContractViolationError, LLMCallError
from agents.image_generator.contract import ImageAsset, ImageGenInput, build_image_prompt
from agents.image_generator.validator import validate_image_file
from llm.gemini_image_client import GeminiImageClient
from utils.logger import get_logger

logger = get_logger("agents.image_generator")


class ImageGenerationAgent:
    def __init__(self, client: GeminiImageClient, output_dir: Path):
        self.client = client
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((LLMCallError, ContractViolationError)),
        reraise=True,
    )
    def _generate_and_validate(self, input_data: ImageGenInput) -> Path:
        prompt = build_image_prompt(input_data)
        image_bytes = self.client.generate_image(prompt)

        file_path = self.output_dir / f"scene_{input_data.scene_id}.png"
        file_path.write_bytes(image_bytes)

        return validate_image_file(file_path)

    def generate(self, input_data: ImageGenInput) -> ImageAsset:
        logger.info(f"[image_generator] Starting run for scene {input_data.scene_id}")
        try:
            file_path = self._generate_and_validate(input_data)
            logger.info(f"[image_generator] Completed successfully for scene {input_data.scene_id}")
            return ImageAsset(
                scene_id=input_data.scene_id,
                file_path=str(file_path),
                prompt_used=input_data.base_prompt,
            )
        except Exception as e:
            logger.error(f"[image_generator] Failed after retries for scene {input_data.scene_id}: {e}")
            raise