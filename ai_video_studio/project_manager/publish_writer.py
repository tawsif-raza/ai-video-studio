# The Publishing Engine's own writer, owned by Project Manager (ARCHITECTURE.md
# SS4/SS24), mirroring render_writer.py's convention: each report shape is
# defined once in shared_core/contracts, and this module only serializes an
# instance of it to disk. Deliberately kept separate from
# PublishingEngineController and from platform adapters themselves - neither
# touches project_manager (their established boundary), so the caller
# (publish_app.py, or any future orchestration entry point) runs the engine,
# then hands the typed result here to persist it.
#
# Four files, four different moments:
# - publish_validation.json (Milestone P2): the PREFLIGHT-only
#   PublishValidationReport - project state, video, and metadata checks,
#   no platform/credential/network involvement at all. Written by
#   ProjectManager.check_publish_readiness.
# - publish_report.json (Milestone P6): the FULL PublishingEngineController
#   orchestration result - readiness + credential structure + real
#   authentication outcome + the overall ready_to_publish verdict. Written
#   by ProjectManager.save_publish_report.
# - upload_report.json (Milestone P7.2): the actual upload attempt's PROCESS
#   outcome (PublishResult) - did every byte get accepted, bytes
#   transferred, the resulting external_video_id if any. success=True here
#   means only that the HTTP transfer succeeded - it is NOT, by itself, a
#   successful publish. Written by ProjectManager.save_upload_result.
# - upload_verification.json (Milestone P7.2): whether the uploaded video
#   could actually be retrieved via the platform's API afterward - the
#   required second check a successful upload must never skip. Written by
#   the same call, only when there was an upload to verify. This is a
#   narrow foundation, not full postflight verification (processing status,
#   duration, privacy-status confirmation) - that remains a later,
#   separate milestone, along with the PUBLISHED state transition.

from pathlib import Path
from typing import Optional

from shared_core.contracts.publish import PublishResult, PublishValidationReport, ReadyToPublishResult
from config import settings


def write_publish_validation(*, project_id: str, validation_report: PublishValidationReport) -> Path:
    publish_dir = settings.OUTPUT_DIR / "projects" / project_id / "publishing"
    publish_dir.mkdir(parents=True, exist_ok=True)
    (publish_dir / "publish_validation.json").write_text(validation_report.model_dump_json(indent=2))
    return publish_dir


def write_publish_report(*, project_id: str, result: ReadyToPublishResult) -> Path:
    publish_dir = settings.OUTPUT_DIR / "projects" / project_id / "publishing"
    publish_dir.mkdir(parents=True, exist_ok=True)
    (publish_dir / "publish_report.json").write_text(result.model_dump_json(indent=2))
    return publish_dir


def write_upload_report(*, project_id: str, upload_result: PublishResult) -> Path:
    publish_dir = settings.OUTPUT_DIR / "projects" / project_id / "publishing"
    publish_dir.mkdir(parents=True, exist_ok=True)
    (publish_dir / "upload_report.json").write_text(upload_result.model_dump_json(indent=2))
    return publish_dir


def write_upload_verification(*, project_id: str, verification: PublishValidationReport) -> Path:
    publish_dir = settings.OUTPUT_DIR / "projects" / project_id / "publishing"
    publish_dir.mkdir(parents=True, exist_ok=True)
    (publish_dir / "upload_verification.json").write_text(verification.model_dump_json(indent=2))
    return publish_dir
