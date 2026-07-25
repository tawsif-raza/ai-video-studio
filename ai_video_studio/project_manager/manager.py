import hashlib
import json
from pathlib import Path
from typing import List, Optional

from shared_core.contracts.asset_manifest import ImportedMediaManifest, ScannedMediaFile, ValidatedAssetManifest
from shared_core.contracts.camera_plan import CameraPlan
from shared_core.contracts.character_sheet import CharacterSheet
from shared_core.contracts.environment_sheet import EnvironmentSheet
from shared_core.contracts.production_plan import ProductionPlan
from shared_core.contracts.prompt_set import PromptSet
from shared_core.contracts.research import ResearchBrief
from shared_core.contracts.shot_plan import ShotPlan
from shared_core.contracts.editing_plan import EditingPlan
from shared_core.contracts.music_plan import MusicPlan, SceneMood
from shared_core.contracts.publishing_metadata import PublishingPlan
from shared_core.contracts.thumbnail_plan import ThumbnailPlan
from shared_core.contracts.storyboard import Storyboard
from shared_core.contracts.subtitle import SubtitlePlan
from shared_core.contracts.timeline import ShotDuration, Timeline
from shared_core.contracts.voice_script import VoiceScript
from config import settings
from project_manager.package_writer import write_production_package
from project_manager.producer_package_writer import write_producer_package
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

    def load_prompt_set(self, project: Project) -> PromptSet:
        """Reconstructs the PromptSet a completed Director Studio run produced,
        for Producer Studio to consume in a later, separate process invocation
        (ARCHITECTURE.md SS11: Project Manager loads a project requiring state
        >= PACKAGE_READY). Reads the same legacy flat file save_prompt_set()
        wrote, keyed by the id already recorded on the project."""
        if not project.source_prompt_set_id:
            raise ValueError(f"Project {project.project_id} has no prompt set yet - run Director Studio first")
        path = settings.OUTPUT_DIR / f"prompt_set_{project.source_prompt_set_id}.json"
        return PromptSet(**json.loads(path.read_text()))

    def load_production_plan(self, project: Project) -> ProductionPlan:
        """Reconstructs the ProductionPlan a completed Director Studio run
        produced, for a later, separate Producer Studio process to consume
        (same legacy-flat-file convention as load_prompt_set). Read keyed by
        the plan id already recorded on the project - carries both the story
        fields and the character roles Thumbnail Planning needs."""
        if not project.source_plan_id:
            raise ValueError(f"Project {project.project_id} has no production plan yet - run Director Studio first")
        path = settings.OUTPUT_DIR / f"production_plan_{project.source_plan_id}.json"
        return ProductionPlan(**json.loads(path.read_text()))

    def load_character_sheet(self, project: Project) -> CharacterSheet:
        """Reconstructs the CharacterSheet (the Character Bible) from the same
        legacy flat file save_character_sheet wrote - the full typed object,
        not the human-readable Production Package projection, since Thumbnail
        Planning needs each profile's paste-ready reference_prompt verbatim."""
        if not project.source_character_sheet_id:
            raise ValueError(f"Project {project.project_id} has no character sheet yet - run Director Studio first")
        path = settings.OUTPUT_DIR / f"character_sheet_{project.source_character_sheet_id}.json"
        return CharacterSheet(**json.loads(path.read_text()))

    def load_package_metadata(self, project: Project) -> dict:
        """Reads the Production Package's own metadata.json - the 'Project
        Metadata' Publishing Planning consumes. Returned as a plain dict on
        purpose: metadata.json is an ad-hoc package index (package_writer's
        _build_metadata), not a typed contract, so audience/art_style/
        target_duration are read as-is rather than forced into a schema."""
        if not project.production_package_dir:
            raise ValueError(f"Project {project.project_id} has no Production Package yet - run Director Studio first")
        path = Path(project.production_package_dir) / "metadata.json"
        return json.loads(path.read_text())

    def load_shot_durations(self, project: Project) -> List[ShotDuration]:
        """Reads every shot's planned duration back from the Production
        Package's shot_plan.json - unlike PromptSet, ShotPlan itself has no
        reloadable legacy flat file (it's captured in-memory-only during a
        Director Studio run), so Timeline Planning reads the already-written
        Production Package deliverable instead, exactly as ARCHITECTURE.md SS6
        describes Producer Studio's input."""
        if not project.production_package_dir:
            raise ValueError(f"Project {project.project_id} has no Production Package yet - run Director Studio first")
        path = Path(project.production_package_dir) / "shot_plan.json"
        scene_plans = json.loads(path.read_text())
        return [
            ShotDuration(scene_id=scene["scene_id"], shot_id=shot["shot_id"], duration_seconds=shot["duration_seconds"])
            for scene in scene_plans
            for shot in scene["shots"]
        ]

    def load_narration_paragraphs(self, project: Project) -> List[str]:
        """Reads the Production Package's voice_script.txt back into per-scene
        paragraphs - the same ascending scene_id order package_writer's
        _build_voice_script_text() joined them in, and the same order Timeline
        Planning's voice_segments already appear in (both are derived from the
        same ascending scene sequence), so Subtitle Planning can pair the two
        positionally without needing a typed, reloadable VoiceScript (which,
        like ShotPlan, has no legacy flat-file form). Returns an empty list
        when Voice Script was skipped and the package only has the pending
        stub - Subtitle Planning treats that as "no narration text", not an
        error."""
        if not project.production_package_dir:
            raise ValueError(f"Project {project.project_id} has no Production Package yet - run Director Studio first")
        path = Path(project.production_package_dir) / "voice_script.txt"
        text = path.read_text().strip()
        if not text or text.startswith("#"):
            return []
        return [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]

    def load_scene_moods(self, project: Project) -> List[SceneMood]:
        """Reads each scene's mood back from the Production Package's
        scene_plan.json - the same direct-from-package convention
        load_shot_durations() established for ShotPlan, since ProductionPlan
        (like ShotPlan) has a legacy flat file, but Music Planning only needs
        the one field (mood) the Production Package's own scene_plan.json
        already carries."""
        if not project.production_package_dir:
            raise ValueError(f"Project {project.project_id} has no Production Package yet - run Director Studio first")
        path = Path(project.production_package_dir) / "scene_plan.json"
        scenes = json.loads(path.read_text())
        return [SceneMood(scene_id=scene["scene_id"], mood=scene["mood"]) for scene in scenes]

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

    def get_media_dir(self, project: Project) -> Path:
        """Where a human places generated images/video/audio for Producer Studio
        to validate (ARCHITECTURE.md SS10: projects/<id>/media/{images,video,audio}/)."""
        return self._project_dir(project.project_id) / "media"

    def scan_media(self, project: Project) -> ImportedMediaManifest:
        """Builds the typed media inventory Asset Validation receives - the one
        piece of real filesystem access this stage needs, and it belongs here,
        not inside an agent (ARCHITECTURE.md SS5/SS14: studios perform no
        filesystem I/O of their own)."""
        media_dir = self.get_media_dir(project)
        return ImportedMediaManifest(
            images=self._scan_subdir(media_dir / "images"),
            videos=self._scan_subdir(media_dir / "video"),
            audio=self._scan_subdir(media_dir / "audio"),
        )

    def save_asset_manifest(self, project: Project, manifest: ValidatedAssetManifest) -> Project:
        """In-memory-only capture, like save_research_brief/save_voice_script -
        written to disk exactly once as asset_manifest.json inside the Producer
        Package, via export_producer_package(). Only advances state to
        MEDIA_IMPORTED when the manifest actually passed validation - a failed
        Asset Validation run must not silently unblock the rest of Producer
        Studio (ARCHITECTURE.md SS8: MEDIA_IMPORTED means Asset Validation has
        passed, not merely run)."""
        logger.info(f"Asset manifest {manifest.manifest_id} captured for project {project.project_id}")
        if not manifest.is_valid:
            return self._advance(project, source_asset_manifest_id=manifest.manifest_id)
        return self._advance(
            project, status=ProjectState.MEDIA_IMPORTED, source_asset_manifest_id=manifest.manifest_id
        )

    def save_timeline(self, project: Project, timeline: Timeline) -> Project:
        """In-memory-only capture, like save_prompt_set - does not advance
        project.status on its own. ARCHITECTURE.md SS8 defines EDIT_PLAN_READY
        as requiring Timeline, Subtitles, Music Planning, Editing Plan,
        Thumbnail Prompt, and Publishing Metadata to *all* be done; Timeline
        Planning alone landing doesn't earn its own top-level state, exactly
        like Prompt Intelligence alone doesn't reach PROMPTS_COMPLETE without
        Voice Script. Written to disk as timeline_plan.json inside the
        Producer Package, via export_producer_package()."""
        logger.info(f"Timeline {timeline.timeline_id} captured for project {project.project_id}")
        return self._advance(project, source_timeline_id=timeline.timeline_id)

    def save_subtitle_plan(self, project: Project, subtitle_plan: SubtitlePlan) -> Project:
        """In-memory-only capture, like save_timeline - does not advance
        project.status on its own, for the same EDIT_PLAN_READY-requires-every-
        stage reason documented on save_timeline. Written to disk as
        subtitle_plan.json inside the Producer Package, via
        export_producer_package()."""
        logger.info(f"Subtitle plan {subtitle_plan.subtitle_plan_id} captured for project {project.project_id}")
        return self._advance(project, source_subtitle_plan_id=subtitle_plan.subtitle_plan_id)

    def save_music_plan(self, project: Project, music_plan: MusicPlan) -> Project:
        """In-memory-only capture, like save_timeline/save_subtitle_plan -
        does not advance project.status on its own, for the same
        EDIT_PLAN_READY-requires-every-stage reason documented on
        save_timeline. Written to disk as music_plan.json inside the
        Producer Package, via export_producer_package()."""
        logger.info(f"Music plan {music_plan.music_plan_id} captured for project {project.project_id}")
        return self._advance(project, source_music_plan_id=music_plan.music_plan_id)

    def save_editing_plan(self, project: Project, editing_plan: EditingPlan) -> Project:
        """In-memory-only capture, like save_timeline/save_subtitle_plan/
        save_music_plan - does not advance project.status on its own, for the
        same EDIT_PLAN_READY-requires-every-stage reason documented on
        save_timeline. Written to disk as editing_plan.json inside the
        Producer Package, via export_producer_package()."""
        logger.info(f"Editing plan {editing_plan.editing_plan_id} captured for project {project.project_id}")
        return self._advance(project, source_editing_plan_id=editing_plan.editing_plan_id)

    def save_thumbnail_plan(self, project: Project, thumbnail_plan: ThumbnailPlan) -> Project:
        """In-memory-only capture, like save_timeline/save_subtitle_plan/
        save_music_plan/save_editing_plan - does not advance project.status on
        its own, for the same EDIT_PLAN_READY-requires-every-stage reason
        documented on save_timeline. Written to disk as thumbnail_plan.json
        inside the Producer Package, via export_producer_package()."""
        logger.info(f"Thumbnail plan {thumbnail_plan.thumbnail_plan_id} captured for project {project.project_id}")
        return self._advance(project, source_thumbnail_plan_id=thumbnail_plan.thumbnail_plan_id)

    def save_publishing_metadata(self, project: Project, publishing_plan: PublishingPlan) -> Project:
        """The one Producer Studio planning save that DOES advance status:
        Publishing Metadata is the sixth and last of the EDIT_PLAN_READY
        planning sub-stages (Timeline, Subtitle, Music, Editing, Thumbnail all
        deliberately held status at MEDIA_IMPORTED), so by the time this runs
        the other five are already done, exactly as save_voice_script advanced
        to PROMPTS_COMPLETE once Prompt Intelligence had already completed. The
        controller guarantees that ordering; this method trusts it rather than
        re-guarding every prior id, matching the save_voice_script precedent."""
        logger.info(f"Publishing metadata {publishing_plan.publishing_plan_id} captured for project {project.project_id}")
        return self._advance(
            project,
            status=ProjectState.EDIT_PLAN_READY,
            source_publishing_metadata_id=publishing_plan.publishing_plan_id,
        )

    def export_producer_package(
        self,
        project: Project,
        *,
        asset_manifest: ValidatedAssetManifest,
        timeline: Optional[Timeline] = None,
        subtitle_plan: Optional[SubtitlePlan] = None,
        music_plan: Optional[MusicPlan] = None,
        editing_plan: Optional[EditingPlan] = None,
        thumbnail_plan: Optional[ThumbnailPlan] = None,
        publishing_plan: Optional[PublishingPlan] = None,
    ) -> Project:
        package_dir = write_producer_package(
            project_id=project.project_id,
            asset_manifest=asset_manifest,
            timeline=timeline,
            subtitle_plan=subtitle_plan,
            music_plan=music_plan,
            editing_plan=editing_plan,
            thumbnail_plan=thumbnail_plan,
            publishing_plan=publishing_plan,
        )
        logger.info(f"Producer package written to {package_dir}")
        return self._advance(project, producer_package_dir=str(package_dir))

    def _scan_subdir(self, subdir: Path) -> List[ScannedMediaFile]:
        if not subdir.exists():
            return []
        files = []
        for path in sorted(subdir.iterdir()):
            if not path.is_file():
                continue
            data = path.read_bytes()
            files.append(ScannedMediaFile(
                filename=path.name,
                path=str(path),
                size_bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
            ))
        return files

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
