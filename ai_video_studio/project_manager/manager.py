import json
from pathlib import Path
from typing import Optional

from shared_core.contracts.camera_plan import CameraPlan
from shared_core.contracts.character_sheet import CharacterSheet
from shared_core.contracts.environment_sheet import EnvironmentSheet
from shared_core.contracts.production_plan import ProductionPlan
from shared_core.contracts.prompt_set import PromptSet
from shared_core.contracts.research import ResearchBrief
from shared_core.contracts.shot_plan import ShotPlan
from shared_core.contracts.storyboard import Storyboard
from shared_core.contracts.voice_script import VoiceScript
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

    def save_research_brief(self, project: Project, brief: ResearchBrief) -> Project:
        """Unlike the legacy save_* methods below, this writes no flat file -
        the research brief is captured in-memory only, here, and is written
        to disk exactly once, as research_brief.json inside the Production
        Package, when export_production_package() runs. Research Planner
        never sees a path; Project Manager decides where this content lives."""
        logger.info(f"Research brief {brief.brief_id} captured for project {project.project_id}")
        return self._advance(
            project, status=ProjectState.RESEARCHED, source_research_brief_id=brief.brief_id
        )

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

    def save_shot_plan(self, project: Project, shot_plan: ShotPlan) -> Project:
        """Like save_research_brief/save_voice_script, this writes no flat file -
        deliberately not extending the legacy flat-outputs pattern for a brand-new
        stage. The shot plan is captured in-memory only and written to disk exactly
        once, as shot_plan.json inside the Production Package."""
        logger.info(f"Shot plan {shot_plan.shot_plan_id} captured for project {project.project_id}")
        return self._advance(
            project, status=ProjectState.SHOTS_COMPLETE, source_shot_plan_id=shot_plan.shot_plan_id
        )

    def save_camera_plan(self, project: Project, camera_plan: CameraPlan) -> Project:
        """Same in-memory-only convention as save_shot_plan - written to disk exactly
        once, as camera_plan.json inside the Production Package."""
        logger.info(f"Camera plan {camera_plan.camera_plan_id} captured for project {project.project_id}")
        return self._advance(
            project, status=ProjectState.CAMERA_COMPLETE, source_camera_plan_id=camera_plan.camera_plan_id
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
        """Does not advance status to PROMPTS_COMPLETE - ARCHITECTURE.md SS8 defines that
        state as requiring Prompt Intelligence AND Voice Script to both be done. That
        transition belongs to save_voice_script(), which runs after this in the pipeline."""
        path = settings.OUTPUT_DIR / f"prompt_set_{prompt_set.prompt_set_id}.json"
        path.write_text(prompt_set.model_dump_json(indent=2))
        logger.info(f"Prompt set saved to {path}")
        return self._advance(project, source_prompt_set_id=prompt_set.prompt_set_id)

    def save_voice_script(self, project: Project, voice_script: VoiceScript) -> Project:
        """Like save_research_brief, this writes no flat file - the voice script is
        captured in-memory only, here, and is written to disk exactly once, as
        voice_script.txt inside the Production Package, when export_production_package()
        runs. This is the method that advances status to PROMPTS_COMPLETE, since by the
        time it runs, Prompt Intelligence (save_prompt_set) has already completed."""
        logger.info(f"Voice script {voice_script.script_id} captured for project {project.project_id}")
        return self._advance(
            project, status=ProjectState.PROMPTS_COMPLETE, source_voice_script_id=voice_script.script_id
        )

    def export_production_package(
        self,
        project: Project,
        *,
        plan: ProductionPlan,
        storyboard: Storyboard,
        shot_plan: ShotPlan,
        camera_plan: CameraPlan,
        character_sheet: CharacterSheet,
        environment_sheet: EnvironmentSheet,
        prompt_set: PromptSet,
        research_brief: Optional[ResearchBrief] = None,
        voice_script: Optional[VoiceScript] = None,
        tone=None,
        audience=None,
        art_style=None,
    ) -> Project:
        package_dir = write_production_package(
            project_id=project.project_id,
            plan=plan,
            storyboard=storyboard,
            shot_plan=shot_plan,
            camera_plan=camera_plan,
            character_sheet=character_sheet,
            environment_sheet=environment_sheet,
            prompt_set=prompt_set,
            research_brief=research_brief,
            voice_script=voice_script,
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
