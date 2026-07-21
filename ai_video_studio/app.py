import argparse
import json

from agents.character_planner.agent import CharacterPlannerAgent
from agents.character_planner.contract import CharacterPlannerInput
from agents.environment_planner.agent import EnvironmentPlannerAgent
from agents.environment_planner.contract import EnvironmentPlannerInput
from agents.image_generator.agent import ImageGenerationAgent
from agents.image_generator.contract import ImageGenInput
from agents.prompt_generator.agent import PromptGeneratorAgent
from agents.prompt_generator.contract import (
    PromptGeneratorInput,
    PromptSet,
    find_characters_for_shot,
    find_environment_for_scene,
)
from agents.scene_planner.agent import ScenePlannerAgent
from agents.scene_planner.contract import ScenePlannerInput
from agents.story_planner.agent import StoryPlannerAgent
from agents.story_planner.contract import StoryPlannerInput
from config import settings
from llm.groq_client import GroqClient as LLMClient
from llm.gemini_image_client import GeminiImageClient
from utils.logger import get_logger

logger = get_logger("app")


def main():
    parser = argparse.ArgumentParser(description="AI Video Studio")
    parser.add_argument("--idea", required=True, help="Raw story idea / prompt")
    parser.add_argument("--duration", type=int, default=60, help="Target video duration in seconds")
    parser.add_argument("--tone", default=None)
    parser.add_argument("--audience", default=None)
    parser.add_argument("--art-style", default=None, help="e.g. '3D animated, Pixar-style, warm cinematic lighting'")
    parser.add_argument("--skip-images", action="store_true", help="Stop after Prompt Generator, don't call image generation")
    args = parser.parse_args()

    llm = LLMClient()

    # ---- Node 1: Story Planner ----
    story_agent = StoryPlannerAgent(llm)
    story_input = StoryPlannerInput(
        story_idea=args.idea,
        target_duration_seconds=args.duration,
        tone=args.tone,
        audience=args.audience,
    )
    story_result = story_agent.run(story_input)

    if not story_result.success:
        logger.error(f"Story Planner failed: {story_result.error}")
        raise SystemExit(1)

    plan = story_result.data
    plan_path = settings.OUTPUT_DIR / f"production_plan_{plan.plan_id}.json"
    plan_path.write_text(plan.model_dump_json(indent=2))
    logger.info(f"Production plan saved to {plan_path}")

    # ---- Node 2: Scene Planner ----
    scene_agent = ScenePlannerAgent(llm)
    scene_result = scene_agent.run(ScenePlannerInput(production_plan=plan))

    if not scene_result.success:
        logger.error(f"Scene Planner failed: {scene_result.error}")
        raise SystemExit(1)

    storyboard = scene_result.data
    storyboard_path = settings.OUTPUT_DIR / f"storyboard_{storyboard.storyboard_id}.json"
    storyboard_path.write_text(storyboard.model_dump_json(indent=2))
    logger.info(f"Storyboard saved to {storyboard_path}")

    # ---- Node 3: Character Planner ----
    character_agent = CharacterPlannerAgent(llm)
    character_result = character_agent.run(
        CharacterPlannerInput(production_plan=plan, art_style=args.art_style)
    )

    if not character_result.success:
        logger.error(f"Character Planner failed: {character_result.error}")
        raise SystemExit(1)

    character_sheet = character_result.data
    char_sheet_path = settings.OUTPUT_DIR / f"character_sheet_{character_sheet.sheet_id}.json"
    char_sheet_path.write_text(character_sheet.model_dump_json(indent=2))
    logger.info(f"Character sheet saved to {char_sheet_path}")

    # ---- Node 4: Environment Planner ----
    environment_agent = EnvironmentPlannerAgent(llm)
    environment_result = environment_agent.run(
        EnvironmentPlannerInput(production_plan=plan, art_style=args.art_style)
    )

    if not environment_result.success:
        logger.error(f"Environment Planner failed: {environment_result.error}")
        raise SystemExit(1)

    environment_sheet = environment_result.data
    env_sheet_path = settings.OUTPUT_DIR / f"environment_sheet_{environment_sheet.sheet_id}.json"
    env_sheet_path.write_text(environment_sheet.model_dump_json(indent=2))
    logger.info(f"Environment sheet saved to {env_sheet_path}")

    # ---- Node 5: Prompt Generator - runs once per shot ----
    prompt_agent = PromptGeneratorAgent(llm)
    shot_prompts = []

    for scene_plan in storyboard.scene_plans:
        environment_profile = find_environment_for_scene(scene_plan.scene_id, plan, environment_sheet)

        for shot in scene_plan.shots:
            character_profiles = find_characters_for_shot(shot.characters_in_shot, character_sheet)

            shot_input = PromptGeneratorInput(
                scene_id=scene_plan.scene_id,
                shot_id=shot.shot_id,
                shot_description=shot.description,
                camera_angle=shot.camera_angle,
                camera_movement=shot.camera_movement,
                duration_seconds=shot.duration_seconds,
                character_profiles=character_profiles,
                environment_profile=environment_profile,
                art_style=args.art_style,
            )
            shot_result = prompt_agent.run(shot_input)

            if not shot_result.success:
                logger.error(
                    f"Prompt Generator failed on scene {scene_plan.scene_id} shot {shot.shot_id}: "
                    f"{shot_result.error}"
                )
                raise SystemExit(1)

            shot_prompts.append(shot_result.data)
            logger.info(f"Generated prompt for scene {scene_plan.scene_id}, shot {shot.shot_id}")

    prompt_set = PromptSet(source_storyboard_id=storyboard.storyboard_id, shots=shot_prompts)
    prompt_set_path = settings.OUTPUT_DIR / f"prompt_set_{prompt_set.prompt_set_id}.json"
    prompt_set_path.write_text(prompt_set.model_dump_json(indent=2))
    logger.info(f"Prompt set saved to {prompt_set_path}")

    if args.skip_images:
        print(json.dumps(json.loads(prompt_set.model_dump_json()), indent=2))
        return

    # ---- Node 6: Image Generation - one image per scene, using each scene's first shot's prompt ----
    image_client = GeminiImageClient()
    image_agent = ImageGenerationAgent(image_client, output_dir=settings.OUTPUT_DIR / "images")
    image_assets = []

    for scene_plan in storyboard.scene_plans:
        scene_shots = sorted(
            (sp for sp in shot_prompts if sp.scene_id == scene_plan.scene_id),
            key=lambda sp: sp.shot_id,
        )
        if not scene_shots:
            continue
        representative_prompt = scene_shots[0].image_prompt

        image_input = ImageGenInput(
            scene_id=scene_plan.scene_id,
            base_prompt=representative_prompt,
            aspect_ratio="9:16",
        )
        try:
            asset = image_agent.generate(image_input)
        except Exception as e:
            logger.error(f"Image Generation failed on scene {scene_plan.scene_id}: {e}")
            raise SystemExit(1)

        image_assets.append(asset)

    manifest = {"assets": [json.loads(a.model_dump_json()) for a in image_assets]}
    manifest_path = settings.OUTPUT_DIR / "image_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    logger.info(f"Image manifest saved to {manifest_path}")

    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
