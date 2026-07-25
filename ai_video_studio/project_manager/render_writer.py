# The Execution Engine's own writer, owned by Project Manager (ARCHITECTURE.md
# SS4/SS6/SS9), mirroring producer_package_writer.py's convention: report
# shapes are defined once as typed schemas in shared_core/contracts, and this
# module only serializes instances of those types to disk. Two files, kept
# deliberately separate:
#
# - render_report.json: EXECUTION-PROCESS diagnostics (did ffmpeg run OK,
#   exit code, timing, stderr on failure) - written for every attempted
#   (non-dry-run) render, success or failure.
# - render_validation.json: OUTPUT-QUALITY verification (does the rendered
#   file actually match the expected duration/resolution/fps/streams) -
#   written only when a render produced a file to probe.
#
# The video file itself (video.mp4) is written directly by ffmpeg_executor,
# not here - this module only ever writes the two JSON reports alongside it.

from pathlib import Path
from typing import Optional

from shared_core.contracts.render import RenderResult, RenderValidationReport
from config import settings


def write_render_reports(
    *,
    project_id: str,
    render_result: RenderResult,
    validation_report: Optional[RenderValidationReport] = None,
) -> Path:
    render_dir = settings.OUTPUT_DIR / "projects" / project_id / "renders"
    render_dir.mkdir(parents=True, exist_ok=True)

    (render_dir / "render_report.json").write_text(render_result.model_dump_json(indent=2))

    if validation_report is not None:
        (render_dir / "render_validation.json").write_text(validation_report.model_dump_json(indent=2))

    return render_dir
