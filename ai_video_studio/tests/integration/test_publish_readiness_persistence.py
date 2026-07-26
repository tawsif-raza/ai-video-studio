"""
Integration test for Milestone P6: runs the real Publishing Engine
orchestration (preflight -> registry -> credential provider -> authenticate,
Milestone P5) against a real project on disk (via ProjectManager), then
persists the result (Milestone P6) and reads it back from disk - proving the
full P2/P5/P6 pipeline works together, not just each piece in isolation.

The only fake component is the platform adapter itself, so this test makes
zero real network calls while still exercising every real orchestration path
(PublishingEngineController, ProjectManager, the writer, and the on-disk
project layout) for real.
"""

import json

from config import settings
from project_manager.manager import ProjectManager
from project_manager.project import ProjectState
from publishing_engine.controller import PublishingEngineController
from publishing_engine.credentials import CredentialProvider
from publishing_engine.platforms.base import PublishingPlatform
from shared_core.contracts.publish import (
    AuthenticationResult,
    PlatformCredentials,
    PublishValidationCheck,
    PublishValidationReport,
)
from shared_core.contracts.publishing_metadata import PublishingMetadata, PublishingPlan, YouTubeMetadata


class _FakeCredentialProvider(CredentialProvider):
    def load(self, platform: str) -> PlatformCredentials:
        return PlatformCredentials(platform=platform, fields={"client_id": "id", "client_secret": "secret", "refresh_token": "token"})


class _FakePlatform(PublishingPlatform):
    platform_name = "youtube"

    def validate_credentials(self, credentials):
        return PublishValidationReport(
            is_valid=True, platform=self.platform_name,
            checks=[PublishValidationCheck(name="credential_client_id", passed=True, expected="present", actual="id")],
        )

    def authenticate(self, credentials):
        return AuthenticationResult(success=True, platform=self.platform_name, account_label="Integration Test Channel")

    def upload(self, request, credentials, *, progress_callback=None):
        raise AssertionError("upload() must never be called")

    def check_status(self, request, credentials):
        raise AssertionError("check_status() must never be called")


def _set_up_ready_project(manager: ProjectManager):
    project = manager.create_project()

    package_dir = settings.OUTPUT_DIR / "projects" / project.project_id / "producer-package"
    package_dir.mkdir(parents=True)
    plan = PublishingPlan(
        canonical=PublishingMetadata(title="Integration Video", description="D", category="Education", language="en"),
        youtube=YouTubeMetadata(
            title="Integration Video", description="D", category="27", default_language="en", playlist="", visibility="private"
        ),
    )
    (package_dir / "publishing_metadata.json").write_text(plan.model_dump_json())

    video_path = settings.OUTPUT_DIR / "projects" / project.project_id / "renders" / "video.mp4"
    video_path.parent.mkdir(parents=True)
    video_path.write_bytes(b"fake mp4 bytes")

    return project.model_copy(
        update={
            "status": ProjectState.VIDEO_RENDERED,
            "rendered_video_path": str(video_path),
            "producer_package_dir": str(package_dir),
        }
    )


def test_full_readiness_and_persistence_pipeline(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = _set_up_ready_project(manager)

    readiness_request = manager.build_publish_readiness_request(project, platform="youtube")
    publishing_plan = manager.load_publishing_plan(project)

    controller = PublishingEngineController(
        platform_resolver=lambda name: (lambda: _FakePlatform()),
        credential_provider=_FakeCredentialProvider(),
    )
    result = controller.run(readiness_request=readiness_request, publishing_plan=publishing_plan, dry_run=True)

    assert result.ready_to_publish is True  # sanity: the orchestration itself worked

    manager.save_publish_report(project, result)

    publish_dir = tmp_path / "projects" / project.project_id / "publishing"
    saved = json.loads((publish_dir / "publish_report.json").read_text())
    assert saved["ready_to_publish"] is True
    assert saved["authentication"]["account_label"] == "Integration Test Channel"
    assert saved["readiness"]["is_valid"] is True
    assert saved["credentials"]["is_valid"] is True

    # project state was never touched by any part of this pipeline
    persisted_project = json.loads((tmp_path / "projects" / project.project_id / "project.json").read_text())
    assert persisted_project["status"] == "CREATED"


def test_full_pipeline_persists_a_not_ready_result_too(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()  # fresh - not rendered, no producer package

    readiness_request = manager.build_publish_readiness_request(project, platform="youtube")

    controller = PublishingEngineController(
        platform_resolver=lambda name: (lambda: _FakePlatform()),
        credential_provider=_FakeCredentialProvider(),
    )
    result = controller.run(readiness_request=readiness_request, publishing_plan=None, dry_run=True)

    assert result.ready_to_publish is False  # project state check alone fails this

    manager.save_publish_report(project, result)

    saved = json.loads((tmp_path / "projects" / project.project_id / "publishing" / "publish_report.json").read_text())
    assert saved["ready_to_publish"] is False
    assert saved["readiness"]["is_valid"] is False
