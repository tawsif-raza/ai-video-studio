"""
VideoGenerationEngineController - orchestration for the Video Generation
Engine (ARCHITECTURE.md SS25.8), peer to ExecutionEngineController and
PublishingEngineController. Pure sequencing: it performs no filesystem or
subprocess work of its own beyond delegating to the pure request_builder/
preflight/postflight modules, the provider registry, a provider adapter
(boundary), and Project Manager (loads the prompt set and any prior
manifest, hands out the video output dir, persists the manifest). Imports
only shared_core.contracts and project_manager (SS25.1 rule 1) - never
director_studio, producer_studio, execution_engine, or publishing_engine,
and never calls any agent from any studio.

--dry-run means "resolve + validate + authenticate, but never call the
provider": the controller (not a provider adapter) decides whether to
generate at all, returning VideoGenerationResult(dry_run=True) per shot and
skipping postflight/persistence entirely, since nothing was produced to
probe or record - the same rule ExecutionEngineController/
PublishingEngineController already apply to their own --dry-run branch.

Shots that already carry a valid VideoAsset from a prior run are skipped by
default (SS25.8 step 3) - a routine re-run never silently regenerates (and,
for a real provider, re-charges for) an already-succeeded clip.
"""

from typing import Callable, List, Optional, Tuple, Type

from project_manager.project import Project, ProjectState
from shared_core.contracts.video_generation import (
    ProviderInfo,
    ShotMediaSelection,
    VideoAsset,
    VideoGenerationOptions,
    VideoGenerationResult,
    VideoGenerationValidationReport,
)
from utils.logger import get_logger
from video_generation_engine import ffprobe_client
from video_generation_engine.errors import VideoGenerationEnvironmentError, VideoGenerationInputError
from video_generation_engine.postflight import validate_generated_clip
from video_generation_engine.preflight import verify_generation_inputs
from video_generation_engine.prompt_builder import build_video_prompt
from video_generation_engine.provider_registry import resolve_provider
from video_generation_engine.providers.base import VideoGenerationProvider
from video_generation_engine.request_builder import (
    build_generation_request,
    resolve_selected_shots,
    validate_generation_request,
)

logger = get_logger("video_generation_engine.controller")

ELIGIBLE_STATES = (ProjectState.PACKAGE_READY, ProjectState.MEDIA_IMPORTED, ProjectState.EDIT_PLAN_READY)


class VideoGenerationEngineController:
    def __init__(
        self,
        project_manager,
        *,
        provider_resolver: Callable[[str], Type[VideoGenerationProvider]] = resolve_provider,
        prober: Callable[[str], object] = ffprobe_client.probe,
    ):
        self.project_manager = project_manager
        self._resolve_provider = provider_resolver
        self._prober = prober

    def run(
        self,
        *,
        project_id: str,
        selections: List[ShotMediaSelection],
        options: Optional[VideoGenerationOptions] = None,
    ) -> Tuple[Project, ProviderInfo, List[VideoGenerationResult], List[VideoGenerationValidationReport]]:
        """Returns (project, ProviderInfo, results, validation_reports).
        Raises a VideoGenerationError subclass - never SystemExit - for
        anything wrong before generation can even be attempted (environment,
        missing/inconsistent inputs, missing media); a per-shot generation or
        validation outcome is always reported back via the return values
        instead, never raised. The returned project reflects the merged
        video_manifest.json/video_generation_status update whenever at least
        one shot was actually attempted (non-dry-run); otherwise it is
        unchanged."""
        options = options or VideoGenerationOptions()
        project = self.project_manager.load_project(project_id)

        if project.status not in ELIGIBLE_STATES:
            raise VideoGenerationInputError(
                f"Project {project_id} is at status {project.status.value}, not one of "
                f"{[s.value for s in ELIGIBLE_STATES]} - run Director Studio to PACKAGE_READY first."
            )

        prompt_set = self.project_manager.load_prompt_set(project)
        existing_manifest = self.project_manager.load_video_generation_manifest(project)
        already_generated = {
            (asset.scene_id, asset.shot_id) for asset in (existing_manifest.assets if existing_manifest else [])
        }

        pending_selections = [
            selection for selection in selections
            if selection.mode != "video" or (selection.scene_id, selection.shot_id) not in already_generated
        ]
        skipped = sum(
            1 for selection in selections
            if selection.mode == "video" and (selection.scene_id, selection.shot_id) in already_generated
        )
        if skipped:
            logger.info(f"Skipping {skipped} shot(s) that already have a valid generated clip")

        shot_prompts = resolve_selected_shots(prompt_set, pending_selections)

        output_dir = str(self.project_manager.get_media_video_dir(project))
        requests = [
            build_generation_request(shot_prompt, output_dir=output_dir, options=options)
            for shot_prompt in shot_prompts
        ]
        for request in requests:
            validate_generation_request(request)
            verify_generation_inputs(request)

        # ---- Resolve provider and authenticate (the one hard environment gate) ----
        provider_cls = self._resolve_provider(options.provider)
        provider = provider_cls()
        provider_info = provider.authenticate()
        if not provider_info.available:
            raise VideoGenerationEnvironmentError(
                f"Video generation provider '{options.provider}' is not available: "
                f"{provider_info.detail or 'no detail provided'}"
            )
        logger.info(f"Video generation provider ready: provider={options.provider} account={provider_info.account_label}")

        # ---- --dry-run: never call the provider, nothing to persist ----
        if options.dry_run:
            logger.info("Dry run - requests built and validated, provider was not called")
            results = [
                VideoGenerationResult(
                    success=True, dry_run=True, provider=options.provider, scene_id=r.scene_id, shot_id=r.shot_id,
                )
                for r in requests
            ]
            return project, provider_info, results, []

        if not requests:
            # Nothing new to generate (everything was skipped or nothing was
            # selected) - still nothing to persist, mirroring the dry-run
            # branch's "nothing produced, nothing recorded" rule.
            return project, provider_info, [], []

        # ---- Generate + postflight, per shot ----
        results: List[VideoGenerationResult] = []
        reports: List[VideoGenerationValidationReport] = []
        assets: List[VideoAsset] = []
        for request in requests:
            result = provider.generate(request)
            results.append(result)
            if not result.success:
                logger.error(
                    f"Generation failed for scene {request.scene_id} shot {request.shot_id} "
                    f"({result.error_type}): {result.error}"
                )
                continue

            output_path = str(
                self.project_manager.get_media_video_dir(project) / f"scene_{request.scene_id}_shot_{request.shot_id}.mp4"
            )
            probed = self._prober(output_path)
            report = validate_generated_clip(probed, request, output_path=output_path)
            reports.append(report)

            if report.is_valid:
                assets.append(VideoAsset(
                    scene_id=request.scene_id,
                    shot_id=request.shot_id,
                    file_path=output_path,
                    prompt_used=build_video_prompt(request.shot_prompt, request.options),
                    provider=options.provider,
                    external_job_id=result.external_job_id,
                    duration_seconds=report.probed.duration_seconds if report.probed else None,
                ))
                logger.info(f"Postflight validation passed for scene {request.scene_id} shot {request.shot_id}")
            else:
                failed = [check.name for check in report.checks if not check.passed]
                logger.error(f"Postflight validation failed for scene {request.scene_id} shot {request.shot_id}: {failed}")

        # ---- Persist (never advances project.status - Asset Validation remains the sole gate) ----
        project = self.project_manager.save_video_generation_result(
            project, selections=selections, new_assets=assets, results=results, validation_reports=reports,
        )

        return project, provider_info, results, reports
