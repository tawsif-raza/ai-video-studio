import json
from pathlib import Path

from agents.character_planner.contract import CharacterSheet
from agents.environment_planner.contract import EnvironmentSheet
from agents.prompt_generator.contract import PromptSet
from agents.scene_planner.contract import Storyboard
from agents.story_planner.contract import ProductionPlan
from config import settings
from project_manager.package_writer import write_production_package
from project_manager.project import Project, ProjectState
from utils.logger import get_logger

logger = get_logger("app")


class ProjectManager:
    """
    Sole owner of persistence and lifecycle state (ARCHITECTURE.md SS4).
    Director Studio calls into this class and receives back an updated
    Project - it never opens a file itself. get_images_dir() is the one
    exception: it hands out a *location*, not serialization behavior -
    ImageGenerationAgent still decides its own encoding, filenames, and
    does its own writing (legacy behavior, unchanged; scheduled for removal
    in ARCHITECTURE.md SS15 Phase 6, not touched by this milestone).
    """

    def create_project(self) -> Project:
        project = Project()
        self._write_project_file(project)
        logger.info(f"Project {project.project_id} created")
        return project

    def load_project(self, project_id: str) -> Project:
        path = self._project_dir(project_id) / "project.json"
        return Project(**json.loads(path.read_text()))

    def save_story_plan(self, project: Project, plan: ProductionPlan) -> Project:
        path = settings.OUTPUT_DIR / f"production_plan_{plan.plan_id}.json"
        path.write_text(plan.model_dump_json(indent=2))
        logger.info(f"Production plan saved to {path}")
        return self._advance(project, status=ProjectState.STORY_COMPLETE, source_plan_id=plan.plan_id)

    def save_storyboard(self, project: Project, storyboard: Storyboard) -> Project:
        path = settings.OUTPUT_DIR / f"storyboard_{storyboard.storyboard_id}.json"
        path.write_text(storyboard.model_dump_json(indent=2))
        logger.info(f"Storyboard saved to {path}")
        return self._advance(
            project, status=ProjectState.SCENES_COMPLETE, source_storyboard_id=storyboard.storyboard_id
        )

    def save_character_sheet(self, project: Project, character_sheet: CharacterSheet) -> Project:
        path = settings.OUTPUT_DIR / f"character_sheet_{character_sheet.sheet_id}.json"
        path.write_text(character_sheet.model_dump_json(indent=2))
        logger.info(f"Character sheet saved to {path}")
        return self._advance(
            project, status=ProjectState.CHARACTERS_COMPLETE, source_character_sheet_id=character_sheet.sheet_id
        )

    def save_environment_sheet(self, project: Project, environment_sheet: EnvironmentSheet) -> Project:
        path = settings.OUTPUT_DIR / f"environment_sheet_{environment_sheet.sheet_id}.json"
        path.write_text(environment_sheet.model_dump_json(indent=2))
        logger.info(f"Environment sheet saved to {path}")
        return self._advance(
            project,
            status=ProjectState.ENVIRONMENTS_COMPLETE,
            source_environment_sheet_id=environment_sheet.sheet_id,
        )

    def save_prompt_set(self, project: Project, prompt_set: PromptSet) -> Project:
        path = settings.OUTPUT_DIR / f"prompt_set_{prompt_set.prompt_set_id}.json"
        path.write_text(prompt_set.model_dump_json(indent=2))
        logger.info(f"Prompt set saved to {path}")
        return self._advance(
            project, status=ProjectState.PROMPTS_COMPLETE, source_prompt_set_id=prompt_set.prompt_set_id
        )

    def export_production_package(
        self,
        project: Project,
        *,
        plan: ProductionPlan,
        storyboard: Storyboard,
        character_sheet: CharacterSheet,
        environment_sheet: EnvironmentSheet,
        prompt_set: PromptSet,
        tone=None,
        audience=None,
        art_style=None,
    ) -> Project:
        package_dir = write_production_package(
            project_id=project.project_id,
            plan=plan,
            storyboard=storyboard,
            character_sheet=character_sheet,
            environment_sheet=environment_sheet,
            prompt_set=prompt_set,
            tone=tone,
            audience=audience,
            art_style=art_style,
        )
        logger.info(f"Production package written to {package_dir}")
        return self._advance(
            project, status=ProjectState.PACKAGE_READY, production_package_dir=str(package_dir)
        )

    def save_image_manifest(self, project: Project, manifest: dict) -> Project:
        path = settings.OUTPUT_DIR / "image_manifest.json"
        path.write_text(json.dumps(manifest, indent=2))
        logger.info(f"Image manifest saved to {path}")
        return self._advance(project, image_manifest_path=str(path))

    def get_images_dir(self, project: Project) -> Path:
        return settings.OUTPUT_DIR / "images"

    def _project_dir(self, project_id: str) -> Path:
        return settings.OUTPUT_DIR / "projects" / project_id

    def _write_project_file(self, project: Project) -> None:
        project_dir = self._project_dir(project.project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "project.json").write_text(project.model_dump_json(indent=2))

    def _advance(self, project: Project, **updates) -> Project:
        updated = project.model_copy(update=updates)
        self._write_project_file(updated)
        return updated
