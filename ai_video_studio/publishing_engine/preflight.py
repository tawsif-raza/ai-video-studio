"""
Milestone P2 (ARCHITECTURE.md SS24): determines whether a project is ready to
attempt a publish. Validation only - no network communication, no
authentication, no upload, no project-state mutation. Boundary (read-only):
unlike execution_engine's preflight (which only re-confirms paths a caller
already resolved), this module performs its own raw file existence/read/parse
checks - a caller handing it an already-parsed PublishingPlan would silently
defeat "check required fields exist" and "check the metadata file exists",
since a successfully-parsed object already implies both.

Depends only on shared_core and publishing_engine itself (Milestone P2's
explicit boundary) - never project_manager. project_status therefore arrives
as a plain string, not the ProjectState enum.
"""

import json
from pathlib import Path
from typing import Optional

from publishing_engine.errors import PublishInputError
from publishing_engine.platforms.registry import resolve_platform
from shared_core.contracts.publish import PublishReadinessRequest, PublishValidationCheck, PublishValidationReport

REQUIRED_PROJECT_STATE = "VIDEO_RENDERED"
REQUIRED_CANONICAL_FIELDS = ("title", "description", "category")
REQUIRED_YOUTUBE_FIELDS = ("visibility",)


def validate_publish_readiness(request: PublishReadinessRequest) -> PublishValidationReport:
    """Runs every readiness check and returns one structured report. Never
    raises - an unreadable/missing/malformed input is a failed check, not an
    exception, the same "reportable, not exceptional" convention
    postflight.validate_render already established for the Execution Engine."""
    checks = [_check_project_state(request.project_status)]

    video_exists = _check_video_exists(request.video_path)
    checks.append(video_exists)
    checks.append(_check_video_readable(request.video_path, exists=video_exists.passed))

    metadata_exists, metadata = _check_metadata_exists(request.publishing_metadata_path)
    checks.append(metadata_exists)
    checks.extend(_check_required_fields(metadata))

    checks.append(_check_platform_supported(request.platform))
    checks.append(_check_publishing_configuration(request))

    return PublishValidationReport(
        is_valid=all(check.passed for check in checks),
        checks=checks,
        platform=request.platform,
    )


def _check_project_state(project_status: str) -> PublishValidationCheck:
    return PublishValidationCheck(
        name="project_state",
        passed=project_status == REQUIRED_PROJECT_STATE,
        expected=REQUIRED_PROJECT_STATE,
        actual=project_status or "(unset)",
    )


def _check_video_exists(video_path: str) -> PublishValidationCheck:
    exists = bool(video_path) and Path(video_path).is_file()
    return PublishValidationCheck(
        name="video_exists",
        passed=exists,
        expected="rendered video file present",
        actual="present" if exists else "missing",
    )


def _check_video_readable(video_path: str, *, exists: bool) -> PublishValidationCheck:
    if not exists:
        return PublishValidationCheck(
            name="video_readable", passed=False, expected="readable", actual="file does not exist"
        )
    try:
        with open(video_path, "rb") as handle:
            handle.read(1)
        return PublishValidationCheck(name="video_readable", passed=True, expected="readable", actual="readable")
    except OSError as e:
        return PublishValidationCheck(name="video_readable", passed=False, expected="readable", actual=str(e))


def _check_metadata_exists(metadata_path: str) -> tuple[PublishValidationCheck, Optional[dict]]:
    if not metadata_path or not Path(metadata_path).is_file():
        return (
            PublishValidationCheck(
                name="metadata_exists", passed=False, expected="publishing_metadata.json present", actual="missing"
            ),
            None,
        )
    try:
        data = json.loads(Path(metadata_path).read_text())
    except (OSError, json.JSONDecodeError) as e:
        return (
            PublishValidationCheck(
                name="metadata_exists",
                passed=False,
                expected="publishing_metadata.json present and valid JSON",
                actual=f"unreadable/invalid JSON: {e}",
            ),
            None,
        )
    return (
        PublishValidationCheck(
            name="metadata_exists", passed=True, expected="publishing_metadata.json present", actual="present"
        ),
        data,
    )


def _check_required_fields(metadata: Optional[dict]) -> list[PublishValidationCheck]:
    """canonical.{title,description,category} are platform-agnostic
    (PublishingMetadata); visibility only exists on the YouTube-specific
    projection (YouTubeMetadata) - canonical has no visibility concept at
    all (ARCHITECTURE.md SS24.3/publishing_metadata.py)."""
    canonical = (metadata or {}).get("canonical") or {}
    youtube = (metadata or {}).get("youtube") or {}
    checks = []
    for field in REQUIRED_CANONICAL_FIELDS:
        value = canonical.get(field)
        checks.append(_field_check(f"metadata_{field}", value))
    for field in REQUIRED_YOUTUBE_FIELDS:
        value = youtube.get(field)
        checks.append(_field_check(f"metadata_{field}", value))
    return checks


def _field_check(name: str, value) -> PublishValidationCheck:
    present = isinstance(value, str) and value.strip() != ""
    return PublishValidationCheck(
        name=name,
        passed=present,
        expected="non-empty value",
        actual=repr(value) if value is not None else "missing",
    )


def _check_platform_supported(platform: str) -> PublishValidationCheck:
    try:
        resolve_platform(platform)
        return PublishValidationCheck(
            name="platform_supported", passed=True, expected="registered platform", actual=platform
        )
    except PublishInputError as e:
        return PublishValidationCheck(name="platform_supported", passed=False, expected="registered platform", actual=str(e))


def _check_publishing_configuration(request: PublishReadinessRequest) -> PublishValidationCheck:
    """Confirms the request itself is structurally complete enough to
    eventually attempt a publish - no credentials, no config.py reads, no
    network activity. What "complete" means: a platform is named, a video
    path is set, and an output location is known."""
    missing = [
        field
        for field, value in (("platform", request.platform), ("video_path", request.video_path), ("output_dir", request.output_dir))
        if not value
    ]
    return PublishValidationCheck(
        name="publishing_configuration",
        passed=not missing,
        expected="platform, video_path, and output_dir all set",
        actual="complete" if not missing else f"missing: {', '.join(missing)}",
    )
