from agents.asset_validator.agent import AssetValidatorAgent
from agents.asset_validator.contract import AssetValidatorInput
from agents.editing_planner.agent import EditingPlannerAgent
from agents.editing_planner.contract import EditingPlannerInput
from agents.music_planner.agent import MusicPlannerAgent
from agents.music_planner.contract import MusicPlannerInput
from agents.publishing_planner.agent import PublishingPlannerAgent
from agents.publishing_planner.contract import PublishingPlannerInput
from agents.subtitle_planner.agent import SubtitlePlannerAgent
from agents.subtitle_planner.contract import SubtitlePlannerInput
from agents.thumbnail_planner.agent import ThumbnailPlannerAgent
from agents.thumbnail_planner.contract import ThumbnailPlannerInput
from agents.timeline_planner.agent import TimelinePlannerAgent
from agents.timeline_planner.contract import TimelinePlannerInput
from project_manager.project import ProjectState
from utils.logger import get_logger

logger = get_logger("producer_app")


class ProducerStudioController:
    """Single orchestration entrypoint for the Producer Studio pipeline:
    Asset Validation -> Timeline Planning -> Subtitle Planning -> Music
    Planning -> Editing Planning -> Thumbnail Planning -> Publishing Metadata
    (all seven implemented; the last six are the EDIT_PLAN_READY planning
    sub-stages) -> FFmpeg Export (a future milestone - ARCHITECTURE.md SS15
    Phase 12). This milestone completes the full planning pipeline: a
    successful run ends at EDIT_PLAN_READY.

    Pure sequencing only, same convention as DirectorStudioController - this
    class performs no filesystem operations of its own. Project Manager loads
    the project, scans media, reads the Production Package, and persists
    every result.
    """

    def __init__(self, project_manager):
        self.project_manager = project_manager

    def run(self, *, project_id: str):
        project = self.project_manager.load_project(project_id)

        if project.status not in (
            ProjectState.PACKAGE_READY, ProjectState.MEDIA_IMPORTED, ProjectState.EDIT_PLAN_READY
        ):
            logger.error(
                f"Project {project_id} is at status {project.status.value}, not "
                f"PACKAGE_READY - run Director Studio to completion first."
            )
            raise SystemExit(1)

        # ---- Asset Validation ----
        prompt_set = self.project_manager.load_prompt_set(project)
        imported_media = self.project_manager.scan_media(project)

        asset_validator = AssetValidatorAgent()
        result = asset_validator.run(
            AssetValidatorInput(prompt_set=prompt_set, imported_media=imported_media)
        )

        if not result.success:
            logger.error(f"Asset Validation failed: {result.error}")
            raise SystemExit(1)

        manifest = result.data
        project = self.project_manager.save_asset_manifest(project, manifest)

        if not manifest.is_valid:
            logger.warning(
                f"Asset Validation found {len(manifest.issues)} issue(s) - "
                f"media/ is incomplete, project state was not advanced."
            )
            return project, manifest, None, None, None, None, None, None

        # ---- Timeline Planning ----
        shot_durations = self.project_manager.load_shot_durations(project)
        timeline_planner = TimelinePlannerAgent()
        timeline_result = timeline_planner.run(
            TimelinePlannerInput(asset_manifest=manifest, shot_durations=shot_durations)
        )

        if not timeline_result.success:
            logger.error(f"Timeline Planning failed: {timeline_result.error}")
            raise SystemExit(1)

        timeline = timeline_result.data
        project = self.project_manager.save_timeline(project, timeline)

        # ---- Subtitle Planning ----
        narration_paragraphs = self.project_manager.load_narration_paragraphs(project)
        subtitle_planner = SubtitlePlannerAgent()
        subtitle_result = subtitle_planner.run(
            SubtitlePlannerInput(timeline=timeline, narration_paragraphs=narration_paragraphs)
        )

        if not subtitle_result.success:
            logger.error(f"Subtitle Planning failed: {subtitle_result.error}")
            raise SystemExit(1)

        subtitle_plan = subtitle_result.data
        project = self.project_manager.save_subtitle_plan(project, subtitle_plan)

        # ---- Music Planning ----
        scene_moods = self.project_manager.load_scene_moods(project)
        music_planner = MusicPlannerAgent()
        music_result = music_planner.run(
            MusicPlannerInput(timeline=timeline, subtitle_plan=subtitle_plan, scene_moods=scene_moods)
        )

        if not music_result.success:
            logger.error(f"Music Planning failed: {music_result.error}")
            raise SystemExit(1)

        music_plan = music_result.data
        project = self.project_manager.save_music_plan(project, music_plan)

        # ---- Editing Planning ----
        editing_planner = EditingPlannerAgent()
        editing_result = editing_planner.run(
            EditingPlannerInput(
                asset_manifest=manifest, timeline=timeline, subtitle_plan=subtitle_plan, music_plan=music_plan
            )
        )

        if not editing_result.success:
            logger.error(f"Editing Planning failed: {editing_result.error}")
            raise SystemExit(1)

        editing_plan = editing_result.data
        project = self.project_manager.save_editing_plan(project, editing_plan)

        # ---- Thumbnail Planning ----
        production_plan = self.project_manager.load_production_plan(project)
        character_sheet = self.project_manager.load_character_sheet(project)
        thumbnail_planner = ThumbnailPlannerAgent()
        thumbnail_result = thumbnail_planner.run(
            ThumbnailPlannerInput(
                editing_plan=editing_plan, production_plan=production_plan, character_sheet=character_sheet
            )
        )

        if not thumbnail_result.success:
            logger.error(f"Thumbnail Planning failed: {thumbnail_result.error}")
            raise SystemExit(1)

        thumbnail_plan = thumbnail_result.data
        project = self.project_manager.save_thumbnail_plan(project, thumbnail_plan)

        # ---- Publishing Metadata ----
        package_metadata = self.project_manager.load_package_metadata(project)
        publishing_planner = PublishingPlannerAgent()
        publishing_result = publishing_planner.run(
            PublishingPlannerInput(
                editing_plan=editing_plan,
                thumbnail_plan=thumbnail_plan,
                production_plan=production_plan,
                audience=package_metadata.get("audience"),
            )
        )

        if not publishing_result.success:
            logger.error(f"Publishing Metadata failed: {publishing_result.error}")
            raise SystemExit(1)

        publishing_plan = publishing_result.data
        # save_publishing_metadata is the stage that advances status to EDIT_PLAN_READY
        project = self.project_manager.save_publishing_metadata(project, publishing_plan)
        project = self.project_manager.export_producer_package(
            project, asset_manifest=manifest, timeline=timeline, subtitle_plan=subtitle_plan,
            music_plan=music_plan, editing_plan=editing_plan, thumbnail_plan=thumbnail_plan,
            publishing_plan=publishing_plan,
        )

        return (
            project, manifest, timeline, subtitle_plan, music_plan, editing_plan, thumbnail_plan, publishing_plan
        )
