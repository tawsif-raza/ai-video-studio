import hashlib
import json
import shutil
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
from shared_core.contracts.publish import (
    PublishReadinessRequest,
    PublishResult,
    PublishValidationReport,
    ReadyToPublishResult,
)
from shared_core.contracts.publishing_metadata import PublishingPlan
from shared_core.contracts.render import RenderResult, RenderValidationReport
from shared_core.contracts.thumbnail_plan import ThumbnailPlan
from shared_core.contracts.storyboard import Storyboard
from shared_core.contracts.subtitle import SubtitlePlan
from shared_core.contracts.timeline import ShotDuration, Timeline
from shared_core.contracts.voice_script import VoiceScript
from config import settings
from publishing_engine.preflight import validate_publish_readiness
from project_manager.package_writer import write_production_package
from project_manager.producer_package_writer import write_producer_package
from project_manager.project import Project, ProjectState
from project_manager.publish_writer import (
    write_publish_report,
    write_publish_validation,
    write_upload_report,
    write_upload_verification,
)
from project_manager.render_writer import write_render_reports
from utils.logger import get_logger

logger = get_logger("app")

# Deliberately duplicated, not imported, from agents/asset_validator/validator.py's
# IMAGE_EXTENSIONS/VIDEO_EXTENSIONS/AUDIO_EXTENSIONS: ARCHITECTURE.md SS19 verifies
# project_manager/ depends only on shared_core/ - importing from agents/ here would
# be a new, undocumented edge in that graph. Three small extension sets are cheap
# to duplicate and risk drifting out of sync; that tradeoff is intentional (see
# Milestone W3's technical debt notes) rather than widening the dependency boundary
# for save_uploaded_media() alone.
_UPLOAD_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg"}
_UPLOAD_VIDEO_EXTENSIONS = {"mp4", "mov"}
_UPLOAD_AUDIO_EXTENSIONS = {"wav", "mp3", "m4a"}


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

    def __init__(self) -> None:
        # Milestone W10: memoizes scan_media()'s per-file sha256 by
        # (size, mtime_ns) so a dashboard that calls GET .../media
        # repeatedly (e.g. after every upload in a large batch) doesn't
        # re-read and re-hash every already-scanned file's full bytes each
        # time - only a cheap stat() for files that haven't changed. Safe to
        # hold on the instance: get_project_manager() (web_api/dependencies.py)
        # already keeps exactly one ProjectManager per process via
        # @lru_cache, the same lifetime this cache needs. Keyed by absolute
        # path string, which is unique across every project's media dir.
        self._media_hash_cache: dict[str, tuple[int, int, str]] = {}

    def create_project(self) -> Project:
        project = Project()
        self._write_project_file(project)
        logger.info(f"Project {project.project_id} created")
        return project

    def load_project(self, project_id: str) -> Project:
        path = self._project_dir(project_id) / "project.json"
        return Project(**json.loads(path.read_text()))

    def list_projects(self) -> List[Project]:
        """Additive capability for the Web Dashboard (WEB_DASHBOARD_ARCHITECTURE.md
        SS6): the CLI surface never needed this - a human running app.py already
        knows the project_id it printed - but a dashboard's project list has no
        argv equivalent. Reads exactly what load_project reads, once per project
        directory; introduces no new file format or second source of truth.
        Directories without a project.json (e.g. mid-write, or foreign contents)
        are skipped rather than raising, since a listing endpoint should degrade
        gracefully instead of failing for one bad entry. Newest first."""
        projects_root = settings.OUTPUT_DIR / "projects"
        if not projects_root.exists():
            return []
        projects = []
        for project_dir in projects_root.iterdir():
            if not project_dir.is_dir():
                continue
            project_file = project_dir / "project.json"
            if not project_file.exists():
                continue
            projects.append(Project(**json.loads(project_file.read_text())))
        return sorted(projects, key=lambda p: p.created_at, reverse=True)

    def delete_project(self, project_id: str) -> None:
        """Additive capability: v1.0's CLIs never needed to delete a project,
        so there was no precedent to reuse (ARCHITECTURE.md documents no such
        method). Removes the project's entire directory tree under
        OUTPUT_DIR/projects/<id> - production package, producer package,
        media, renders, and publishing output alike - in one step, since none
        of those are meaningful without the project.json that anchors them.
        Irreversible; the caller (web_api's DELETE /projects/{id}) is
        responsible for confirming intent before calling this. Loads the
        project first so a missing project_id fails the same way load_project
        already does, rather than silently no-op'ing on rmtree's behalf."""
        self.load_project(project_id)
        shutil.rmtree(self._project_dir(project_id))

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

    def load_production_package(self, project: Project) -> dict:
        """Milestone W7.5: reads back every file the Production Package's
        own manifest.json already lists (package_writer.py) - manifest.json
        is reused as the single source of truth for which files exist,
        rather than a second, hardcoded file list living here too. Each
        JSON file is parsed and returned as-is; each .md/.txt file is
        returned as plain text. This introduces no new serialization -
        every file was already fully serialized (either a direct
        model.model_dump_json() dump, or a hand-built projection like
        scene_plan.json) by package_writer at export time; this only reads
        it back. manifest.json's own content is included too, under its
        own filename key, since it's real package content in its own
        right."""
        if not project.production_package_dir:
            raise ValueError(f"Project {project.project_id} has no Production Package yet - run Director Studio first")
        return self._load_package_contents(Path(project.production_package_dir))

    def _producer_package_file(self, project: Project, filename: str) -> Path:
        if not project.producer_package_dir:
            raise ValueError(
                f"Project {project.project_id} has no Producer Package yet - run Producer Studio first"
            )
        return Path(project.producer_package_dir) / filename

    def load_producer_package(self, project: Project) -> dict:
        """Producer Package analog of load_production_package - same
        manifest-driven read-back, same "no new serialization" guarantee.
        Every file in producer-package/ is a direct contract dump (unlike
        some Production Package files, none of these are hand-built
        projections), so this is a pure passthrough of what
        producer_package_writer.py already wrote."""
        if not project.producer_package_dir:
            raise ValueError(f"Project {project.project_id} has no Producer Package yet - run Producer Studio first")
        return self._load_package_contents(Path(project.producer_package_dir))

    def load_asset_manifest(self, project: Project) -> ValidatedAssetManifest:
        """Reconstructs the ValidatedAssetManifest from the Producer Package's
        asset_manifest.json - the full typed dump save/export wrote, read back
        for the Execution Engine to consume in a separate process."""
        path = self._producer_package_file(project, "asset_manifest.json")
        return ValidatedAssetManifest(**json.loads(path.read_text()))

    def load_editing_plan(self, project: Project) -> EditingPlan:
        """Reconstructs the EditingPlan from the Producer Package's
        editing_plan.json - the render blueprint the Execution Engine compiles."""
        path = self._producer_package_file(project, "editing_plan.json")
        return EditingPlan(**json.loads(path.read_text()))

    def load_producer_timeline(self, project: Project) -> Timeline:
        """Reconstructs the Timeline from the Producer Package's
        timeline_plan.json (named load_producer_timeline to distinguish it from
        the in-memory Timeline the Producer pipeline builds fresh)."""
        path = self._producer_package_file(project, "timeline_plan.json")
        return Timeline(**json.loads(path.read_text()))

    def load_subtitle_plan(self, project: Project) -> SubtitlePlan:
        """Reconstructs the SubtitlePlan from the Producer Package's
        subtitle_plan.json."""
        path = self._producer_package_file(project, "subtitle_plan.json")
        return SubtitlePlan(**json.loads(path.read_text()))

    def load_music_plan(self, project: Project) -> MusicPlan:
        """Reconstructs the MusicPlan from the Producer Package's
        music_plan.json."""
        path = self._producer_package_file(project, "music_plan.json")
        return MusicPlan(**json.loads(path.read_text()))

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

    def save_uploaded_media(self, project: Project, filename: str, content: bytes) -> Path:
        """Additive capability for the Web Dashboard's media upload endpoint
        (WEB_DASHBOARD_ARCHITECTURE.md SS6): the CLI has no equivalent - a
        human places files into media/{images,video,audio}/ directly on
        disk, and scan_media() discovers them. A browser upload has no
        filesystem of its own to place them in, so Project Manager - the
        sole writer of project-owned files - does it here instead.

        Infers the destination subdirectory (images/video/audio - the exact
        names scan_media()/_scan_subdir() already scan) from the filename's
        extension, using the same three extension sets Asset Validation
        enforces. An extension outside all three is rejected immediately
        with ValueError rather than landing in a subdirectory scan_media()
        would never look in - failing loudly here beats a silent, invisible
        upload.

        filename is reduced to its basename (Path.name) before use, the
        same defensive move applied to project_id at the web_api boundary
        (ARCHITECTURE.md SS21 item 4) - an uploaded filename is caller-
        supplied input joined directly into a filesystem path, so a value
        like "../../evil.png" is reduced to just "evil.png" and saved
        inside the target subdirectory, never able to escape it."""
        safe_filename = Path(filename).name
        ext = safe_filename.rsplit(".", 1)[-1].lower() if "." in safe_filename else ""
        if ext in _UPLOAD_IMAGE_EXTENSIONS:
            subdir = "images"
        elif ext in _UPLOAD_VIDEO_EXTENSIONS:
            subdir = "video"
        elif ext in _UPLOAD_AUDIO_EXTENSIONS:
            subdir = "audio"
        else:
            allowed = sorted(_UPLOAD_IMAGE_EXTENSIONS | _UPLOAD_VIDEO_EXTENSIONS | _UPLOAD_AUDIO_EXTENSIONS)
            raise ValueError(f"Unsupported media file extension '.{ext}' for {filename!r} - expected one of {allowed}")

        target_dir = self.get_media_dir(project) / subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / safe_filename
        target_path.write_bytes(content)
        logger.info(f"Uploaded media {safe_filename} saved to {target_path}")
        return target_path

    def delete_uploaded_media(self, project: Project, category: str, filename: str) -> Path:
        """Milestone W10: the delete-side counterpart to save_uploaded_media,
        same division of responsibility - Project Manager is the sole writer
        (and remover) of project-owned files, so a browser-initiated delete
        has to come through here rather than web_api touching the filesystem
        itself.

        category is one of the same three subdirectory names
        save_uploaded_media/scan_media already use ("images"/"video"/"audio"),
        not inferred from filename - the caller (a delete button next to one
        listed file) already knows which category it's deleting, and trusting
        that avoids re-deriving it from an extension that might not round-trip
        cleanly. filename is reduced to its basename first, the same
        path-traversal defense save_uploaded_media applies.

        Raises ValueError for an unrecognized category and FileNotFoundError
        if the file isn't there - both are the caller's (web_api's) job to
        translate into 400/404, exactly as save_uploaded_media's ValueError
        already is. No stale reference to clean up beyond the file itself:
        media has no separate persisted metadata record (scan_media() always
        re-scans the filesystem live), so removing the file alone leaves no
        orphaned reference behind."""
        valid_categories = {"images", "video", "audio"}
        if category not in valid_categories:
            raise ValueError(f"Unknown media category {category!r} - expected one of {sorted(valid_categories)}")

        safe_filename = Path(filename).name
        target_path = self.get_media_dir(project) / category / safe_filename
        if not target_path.is_file():
            raise FileNotFoundError(f"Media file {safe_filename!r} not found in {category}")

        target_path.unlink()
        self._media_hash_cache.pop(str(target_path), None)
        logger.info(f"Deleted uploaded media {target_path}")
        return target_path

    def get_render_dir(self, project: Project) -> Path:
        """Where the FFmpeg Execution Engine writes its output, kept entirely
        separate from the read-only Producer Package (projects/<id>/renders/).
        Hands out the location only - like get_media_dir/get_images_dir, Project
        Manager does not create the directory itself; ffmpeg_executor and
        render_writer each create it on their own first write."""
        return self._project_dir(project.project_id) / "renders"

    def get_publish_dir(self, project: Project) -> Path:
        """Where the Publishing Engine writes its output (projects/<id>/publishing/),
        kept separate from renders/. Hands out the location only, like
        get_render_dir - publish_writer creates the directory on first write."""
        return self._project_dir(project.project_id) / "publishing"

    def build_publish_readiness_request(self, project: Project, *, platform: str = "youtube") -> PublishReadinessRequest:
        """Assembles exactly the typed facts publishing_engine needs (project
        status, the rendered video's path, publishing_metadata.json's path) -
        shared by check_publish_readiness (P2) and publish_app.py (P5) so
        this path-resolution logic exists in exactly one place. Read-only;
        never raises even when the project hasn't reached those stages yet -
        an empty path is simply what an incomplete project looks like, and
        publishing_engine.preflight already reports that as a failed check
        rather than needing a pre-check here."""
        metadata_path = (
            str(Path(project.producer_package_dir) / "publishing_metadata.json")
            if project.producer_package_dir
            else ""
        )
        return PublishReadinessRequest(
            project_status=project.status.value,
            video_path=project.rendered_video_path or "",
            publishing_metadata_path=metadata_path,
            platform=platform,
            output_dir=str(self.get_publish_dir(project)),
        )

    def load_publishing_plan(self, project: Project) -> PublishingPlan:
        """Reconstructs the PublishingPlan from the Producer Package's
        publishing_metadata.json - needed by publish_app.py (Milestone P5)
        to build a complete PublishRequest once a project is confirmed ready."""
        path = self._producer_package_file(project, "publishing_metadata.json")
        return PublishingPlan(**json.loads(path.read_text()))

    def check_publish_readiness(self, project: Project, *, platform: str = "youtube") -> PublishValidationReport:
        """Milestone P2 (ARCHITECTURE.md SS24, Preflight Validation): hands
        build_publish_readiness_request's typed facts to the pure/boundary
        preflight validator - the one place Project Manager calls into the
        Publishing Engine so far, the same direction it already calls into
        the Execution Engine.

        Performs no upload, no authentication, and - deliberately, per this
        milestone's scope - no project.status change; only a future
        milestone's actual upload+verification may ever advance PUBLISHED.
        Always writes publish_validation.json, success or failure, since a
        report on why a project isn't ready yet is itself useful output."""
        request = self.build_publish_readiness_request(project, platform=platform)
        report = validate_publish_readiness(request)
        write_publish_validation(project_id=project.project_id, validation_report=report)
        return report

    def save_publish_report(self, project: Project, result: ReadyToPublishResult) -> Project:
        """Milestone P6 (ARCHITECTURE.md SS24): persists the
        PublishingEngineController's full orchestration result - readiness +
        credential structure + real authentication outcome + the overall
        ready_to_publish verdict - to publish_report.json. Deliberately
        separate from the controller itself, which never touches
        project_manager (its established boundary, unchanged since
        Milestone P2): the caller (publish_app.py) runs the controller, then
        hands the result here to persist it.

        No upload, no YouTube write operation, no thumbnail upload, no
        scheduling, and - deliberately, per this milestone's scope - no
        project.status change: ready_to_publish=True alone does not advance
        PUBLISHED, exactly as a merely-valid render doesn't advance
        VIDEO_RENDERED without independent postflight verification (SS7,
        SS9). Returns the project unchanged - there is nothing new to record
        on the project record itself yet."""
        publish_dir = write_publish_report(project_id=project.project_id, result=result)
        logger.info(f"Publish report written to {publish_dir}")
        return project

    def save_upload_result(
        self,
        project: Project,
        upload_result: PublishResult,
        *,
        verification: Optional[PublishValidationReport] = None,
    ) -> Project:
        """Milestone P7.2 (ARCHITECTURE.md SS24): persists an actual upload
        attempt's outcome - upload_report.json always, upload_verification.json
        only when there was an upload to verify (mirrors save_render_result's
        render_report.json/render_validation.json split exactly). Deliberately
        separate from the platform adapter and from publishing_engine.upload_flow,
        neither of which touches project_manager (their established boundary).

        A successful HTTP upload (upload_result.success=True) is explicitly
        NOT treated as a successful publish here: this method never advances
        project.status, regardless of upload_result.success or
        verification.is_valid. The project is left in its current state
        until a later milestone performs full postflight verification (this
        milestone's verification checks retrievability only, not processing
        status/duration/privacy - see YouTubePlatform.check_status) and adds
        the actual PUBLISHED transition. Returns the project unchanged."""
        write_upload_report(project_id=project.project_id, upload_result=upload_result)
        if verification is not None:
            write_upload_verification(project_id=project.project_id, verification=verification)
        logger.info(f"Upload report written for project {project.project_id}")
        return project

    def save_render_result(
        self,
        project: Project,
        *,
        render_result: RenderResult,
        validation_report: Optional[RenderValidationReport] = None,
    ) -> Project:
        """Writes render_report.json (execution-process diagnostics - always,
        for every attempted non-dry-run render) and render_validation.json
        (output-quality verification - only when a render produced a file to
        probe), kept as two separate files per ARCHITECTURE.md's Execution
        Engine design. Advances project.status to VIDEO_RENDERED if and only
        if BOTH render_result.success AND validation_report.is_valid are
        True - a successful ffmpeg exit alone is not sufficient, exactly as
        save_asset_manifest only advances state when the manifest is actually
        valid, not merely produced. Any other outcome leaves the project
        untouched (no file rewrite, no status change) - there is nothing new
        to persist on the project record itself when a render didn't succeed
        far enough to produce a verified file."""
        render_dir = write_render_reports(
            project_id=project.project_id, render_result=render_result, validation_report=validation_report
        )
        logger.info(f"Render reports written to {render_dir}")

        if render_result.success and validation_report is not None and validation_report.is_valid:
            return self._advance(
                project, status=ProjectState.VIDEO_RENDERED, rendered_video_path=render_result.output_path
            )
        return project

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

    def _load_package_contents(self, package_dir: Path) -> dict:
        """Shared read-back logic for load_production_package and
        load_producer_package (W7.5): parses package_dir/manifest.json to
        learn which files really exist (the same manifest package_writer.py/
        producer_package_writer.py already wrote), then reads each one back
        - JSON files parsed, everything else (story.md, voice_script.txt)
        as plain text - keyed by filename. Never returns a path string;
        only file contents. manifest.json itself is included under its own
        key, since it's real package content too."""
        manifest = json.loads((package_dir / "manifest.json").read_text())
        contents: dict = {"manifest.json": manifest}
        for file_info in manifest["files"]:
            name = file_info["name"]
            path = package_dir / name
            if not path.exists():
                continue
            contents[name] = json.loads(path.read_text()) if name.endswith(".json") else path.read_text()
        return contents

    def _scan_subdir(self, subdir: Path) -> List[ScannedMediaFile]:
        """Milestone W10: reads+hashes a file's full bytes only the first
        time it's seen, or again if it's actually changed since (size or
        mtime differs from the cached fingerprint) - repeat scans of a
        project whose media/ hasn't changed (the common case: a dashboard
        refreshing the Media tab, or re-scanning after a batch upload added
        one new file) cost one stat() per unchanged file instead of a full
        read+sha256. Output is bit-identical to the un-cached version
        either way - Asset Validation's duplicate-content detection (which
        depends on these exact hashes) sees no behavior change."""
        if not subdir.exists():
            return []
        files = []
        for path in sorted(subdir.iterdir()):
            if not path.is_file():
                continue
            stat = path.stat()
            cache_key = str(path)
            cached = self._media_hash_cache.get(cache_key)
            if cached is not None and cached[0] == stat.st_size and cached[1] == stat.st_mtime_ns:
                size_bytes, _, sha256 = cached
            else:
                data = path.read_bytes()
                size_bytes = len(data)
                sha256 = hashlib.sha256(data).hexdigest()
                self._media_hash_cache[cache_key] = (size_bytes, stat.st_mtime_ns, sha256)
            files.append(ScannedMediaFile(
                filename=path.name,
                path=str(path),
                size_bytes=size_bytes,
                sha256=sha256,
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
