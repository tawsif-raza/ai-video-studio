"""
ExecutionEngineController - orchestration for the FFmpeg Execution Engine,
peer to ProducerStudioController. Pure sequencing: it performs no filesystem or
subprocess work of its own beyond delegating to the detector (read-only),
Project Manager (loads contracts, hands out the render dir, persists reports
and the state transition), the pure command_builder/postflight modules, and
the executor/prober boundaries. It imports only shared_core contracts and
project_manager - never any agents - honoring the rule that the engine never
calls Director or Producer Studio agents.

--dry-run means "build + validate + print, but never execute": the controller
(not the executor) decides whether to call it at all, returning a
RenderResult(dry_run=True) built here and skipping postflight/persistence
entirely, since nothing was produced to probe or record.

Milestone 8.4 adds postflight: once execution succeeds, the rendered file is
probed (ffprobe_client) and judged against the render's own expected profile
(postflight.validate_render), producing a RenderValidationReport. Project
Manager persists render_report.json (process diagnostics) and
render_validation.json (output-quality verdict) as two separate files, and
advances project.status to VIDEO_RENDERED if and only if BOTH the execution
succeeded AND the validation passed - a successful ffmpeg exit alone was
never sufficient (see ffmpeg_executor's and RenderResult's docstrings).
"""

from execution_engine.command_builder import build_command, validate_render_request
from execution_engine.errors import ExecutionEnvironmentError, RenderInputError
from execution_engine.ffmpeg_detector import detect_ffmpeg
from execution_engine.ffmpeg_executor import execute
from execution_engine.ffprobe_client import probe
from execution_engine.music_library import load_library_index, resolve_music_asset
from execution_engine.postflight import validate_render
from execution_engine.preflight import verify_media_exists
from execution_engine.segmented_renderer import execute_segmented, should_segment
from project_manager.project import ProjectState
from shared_core.contracts.render import RenderOptions, RenderRequest, RenderResult
from utils.logger import get_logger

logger = get_logger("render_app")


class ExecutionEngineController:
    def __init__(self, project_manager, detector=detect_ffmpeg, executor=execute, prober=probe):
        self.project_manager = project_manager
        self.detector = detector
        self.executor = executor
        self.prober = prober

    def run(self, *, project_id: str, options=None):
        """Returns (project, FFmpegInfo, FFmpegCommandSpec, RenderResult,
        RenderValidationReport | None). Raises a RenderError subclass - never
        SystemExit - for anything wrong before execution can even be attempted
        (environment, missing/inconsistent inputs, missing media); an
        execution-phase or validation outcome is always reported back via the
        return values instead, never raised. The returned project reflects the
        VIDEO_RENDERED transition when (and only when) both execution and
        postflight validation succeeded; otherwise it is unchanged."""
        options = options or RenderOptions()
        project = self.project_manager.load_project(project_id)

        if project.status != ProjectState.EDIT_PLAN_READY:
            raise RenderInputError(
                f"Project {project_id} is at status {project.status.value}, not EDIT_PLAN_READY - "
                f"run Producer Studio to completion first."
            )

        # ---- Detect FFmpeg ----
        ffmpeg_info = self.detector()
        if not ffmpeg_info.available:
            raise ExecutionEnvironmentError(
                "FFmpeg was not found on PATH or failed to report its version - install ffmpeg "
                "and ensure it is runnable before rendering."
            )
        logger.info(f"FFmpeg detected: version={ffmpeg_info.version} path={ffmpeg_info.path}")

        # ---- Load every Producer Package input (Project Manager owns this I/O) ----
        music_plan = self.project_manager.load_music_plan(project)

        # ---- Resolve a music asset (ARCHITECTURE.md SS21 item 9) ----
        # load_library_index is the boundary read; resolve_music_asset is
        # pure. Neither raises - no match (or an empty/missing library)
        # simply resolves to None, and every step downstream (preflight,
        # command_builder) already treats that as "narration-only render",
        # not an error.
        music_asset_path = resolve_music_asset(music_plan, load_library_index())
        if music_asset_path:
            logger.info(f"Resolved music asset for mixing: {music_asset_path}")
        else:
            logger.info("No matching music asset resolved - narration-only render")

        request = RenderRequest(
            editing_plan=self.project_manager.load_editing_plan(project),
            asset_manifest=self.project_manager.load_asset_manifest(project),
            timeline=self.project_manager.load_producer_timeline(project),
            subtitle_plan=self.project_manager.load_subtitle_plan(project),
            music_plan=music_plan,
            output_dir=str(self.project_manager.get_render_dir(project)),
            options=options,
            music_asset_path=music_asset_path,
        )

        # ---- Validate inputs (contracts, then media existence) ----
        validate_render_request(request)
        verify_media_exists(request)

        # ---- Build the command object ----
        command_spec = build_command(request)
        logger.info(
            f"Built FFmpeg command: {len(command_spec.inputs)} input(s), "
            f"filter_complex={'present' if command_spec.filter_complex else 'absent'}"
        )

        # ---- --dry-run: never execute, nothing to persist ----
        if options.dry_run:
            logger.info("Dry run - command built and validated, ffmpeg was not invoked")
            return project, ffmpeg_info, command_spec, RenderResult(success=True, dry_run=True), None

        # ---- Execute ----
        # Many-scene edits (several crossfade boundaries) are routed through
        # the segmented renderer instead of this single filter_complex path:
        # holding every visual input open in one ffmpeg process is what was
        # observed OOM-killing a real many-scene render on a memory-
        # constrained deployment regardless of output resolution (see
        # segmented_renderer's module docstring). should_segment reads the
        # same editing_plan command_spec was already built from, so this
        # never disagrees with what was just validated/logged above.
        # self.executor is still the seam both paths run every subprocess
        # through, so a caller that fakes it (tests) gets the same fake
        # behavior regardless of which path a given plan takes.
        if should_segment(request.editing_plan):
            logger.info("Editing plan has multiple scene-crossfade boundaries - using segmented render")
            render_result = execute_segmented(
                request, ffmpeg_path=ffmpeg_info.path or "ffmpeg", timeout_seconds=options.timeout_seconds,
                executor=self.executor,
            )
        else:
            logger.info("Executing ffmpeg render")
            render_result = self.executor(
                command_spec, ffmpeg_path=ffmpeg_info.path or "ffmpeg", timeout_seconds=options.timeout_seconds
            )

        # ---- Postflight: only meaningful when there's a file to probe ----
        validation_report = None
        if render_result.success:
            logger.info(
                f"Render succeeded in {render_result.duration_seconds:.1f}s - {render_result.output_path}"
            )
            probed = self.prober(render_result.output_path)
            validation_report = validate_render(
                probed, request.editing_plan, options, output_path=render_result.output_path
            )
            if validation_report.is_valid:
                logger.info("Postflight validation passed")
            else:
                failed = [c.name for c in validation_report.checks if not c.passed]
                logger.error(f"Postflight validation failed: {failed}")
        else:
            logger.error(f"Render failed ({render_result.error_type}): {render_result.error}")

        # ---- Persist reports and (only on full success) advance state ----
        project = self.project_manager.save_render_result(
            project, render_result=render_result, validation_report=validation_report
        )

        return project, ffmpeg_info, command_spec, render_result, validation_report
