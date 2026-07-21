import json

from agents.character_planner.agent import CharacterPlannerAgent
from agents.character_planner.contract import CharacterPlannerInput
from agents.environment_planner.agent import EnvironmentPlannerAgent
from agents.environment_planner.contract import EnvironmentPlannerInput
from agents.image_generator.agent import ImageGenerationAgent
from agents.image_generator.contract import ImageGenInput
from agents.prompt_generator.agent import PromptGeneratorAgent
from agents.prompt_generator.contract import PromptGeneratorInput, PromptSet
from agents.scene_planner.agent import ScenePlannerAgent
from agents.scene_planner.contract import ScenePlannerInput
from agents.story_planner.agent import StoryPlannerAgent
from agents.story_planner.contract import StoryPlannerInput
from director_studio.pipeline_helpers import select_representative_prompt
from shared_core.lookups import find_characters_for_shot, find_environment_for_scene
from utils.logger import get_logger

logger = get_logger("app")


class DirectorStudioController:
    """Single orchestration entrypoint for the Director Studio pipeline:
    Story Planner -> Scene Planner -> Character Planner -> Environment Planner
    -> Prompt Generator -> Image Generator (temporary until Milestone D).

    Pure sequencing only - constructs each agent, runs it, checks success, and
    passes typed output forward. Business logic (cross-referencing, prompt
    composition, validation) stays inside the agents it was extracted from.
    All persistence goes through ProjectManager - this class performs no
    filesystem operations of its own.
    """

    def __init__(self, llm_client, project_manager):
        self.llm = llm_client
        self.project_manager = project_manager

    def run(
        self,
        *,
        idea,
        duration,
        tone=None,
        audience=None,
        art_style=None,
        skip_images=False,
        image_client_factory=None,
    ):
        llm = self.llm
        project = self.project_manager.create_project()

        # ---- Node 1: Story Planner ----
        story_agent = StoryPlannerAgent(llm)
        story_input = StoryPlannerInput(
            story_idea=idea,
            target_duration_seconds=duration,
            tone=tone,
            audience=audience,
        )
        story_result = story_agent.run(story_input)

        if not story_result.success:
            logger.error(f"Story Planner failed: {story_result.error}")
            raise SystemExit(1)

        plan = story_result.data
        project = self.project_manager.save_story_plan(project, plan)

        # ---- Node 2: Scene Planner ----
        scene_agent = ScenePlannerAgent(llm)
        scene_result = scene_agent.run(ScenePlannerInput(production_plan=plan))

        if not scene_result.success:
            logger.error(f"Scene Planner failed: {scene_result.error}")
            raise SystemExit(1)

        storyboard = scene_result.data
        project = self.project_manager.save_storyboard(project, storyboard)

        # ---- Node 3: Character Planner ----
        character_agent = CharacterPlannerAgent(llm)
        character_result = character_agent.run(
            CharacterPlannerInput(production_plan=plan, art_style=art_style)
        )

        if not character_result.success:
            logger.error(f"Character Planner failed: {character_result.error}")
            raise SystemExit(1)

        character_sheet = character_result.data
        project = self.project_manager.save_character_sheet(project, character_sheet)

        # ---- Node 4: Environment Planner ----
        environment_agent = EnvironmentPlannerAgent(llm)
        environment_result = environment_agent.run(
            EnvironmentPlannerInput(production_plan=plan, art_style=art_style)
        )

        if not environment_result.success:
            logger.error(f"Environment Planner failed: {environment_result.error}")
            raise SystemExit(1)

        environment_sheet = environment_result.data
        project = self.project_manager.save_environment_sheet(project, environment_sheet)

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
                    art_style=art_style,
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
        project = self.project_manager.save_prompt_set(project, prompt_set)

        # ---- Production Package - additive second output, alongside the legacy files above ----
        project = self.project_manager.export_production_package(
            project,
            plan=plan,
            storyboard=storyboard,
            character_sheet=character_sheet,
            environment_sheet=environment_sheet,
            prompt_set=prompt_set,
            tone=tone,
            audience=audience,
            art_style=art_style,
        )

        if skip_images:
            print(json.dumps(json.loads(prompt_set.model_dump_json()), indent=2))
            return

        # ---- Node 6: Image Generation ----
        image_client = image_client_factory()
        images_dir = self.project_manager.get_images_dir(project)
        image_agent = ImageGenerationAgent(image_client, output_dir=images_dir)
        image_assets = []

        for scene_plan in storyboard.scene_plans:
            scene_shots = sorted(
                (sp for sp in shot_prompts if sp.scene_id == scene_plan.scene_id),
                key=lambda sp: sp.shot_id,
            )
            if not scene_shots:
                continue
            representative_prompt = select_representative_prompt(scene_shots)

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
        project = self.project_manager.save_image_manifest(project, manifest)

        print(json.dumps(manifest, indent=2))
        return
