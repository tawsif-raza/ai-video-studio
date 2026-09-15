"""Prerequisite 1 of 3 for the AWS deployment (docs/aws-production-
architecture.md's "before this is provisioned" section): makes a
project's on-disk directory durable across an ECS/Fargate task's ephemeral
local storage by mirroring it to S3.

Deliberately NOT a generic StorageBackend abstraction threaded through
every one of ProjectManager's ~60 methods - that would be a large,
high-risk rewrite of code this system's own architecture rules (§21 in
ARCHITECTURE.md, and AGENTS.md's "preserve existing architecture") say to
extend, not rewrite. Instead, ProjectManager's on-disk behavior is left
completely untouched; S3SyncingProjectManager (s3_syncing_project_manager.py)
wraps it and calls the two methods here - sync_up/ensure_local - around
existing calls. Every one of ProjectManager's own methods, and every
existing test exercising it directly, is unaffected by this file's
existence.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from utils.logger import get_logger

logger = get_logger("storage.s3_project_sync")


class S3ProjectSync:
    """Mirrors one project's directory tree (OUTPUT_DIR/projects/<id>/)
    to/from S3 under the same relative key prefix. Takes an injectable S3
    client so tests can exercise this against a fake in-memory client
    instead of real AWS (see tests/storage/fakes.py), the same convention
    this codebase already uses for LLM clients and controllers."""

    def __init__(self, *, bucket: str, s3_client, projects_root: Path, key_prefix: str = "projects"):
        self.bucket = bucket
        self.s3 = s3_client
        self.projects_root = projects_root
        self.key_prefix = key_prefix

    def _local_dir(self, project_id: str) -> Path:
        return self.projects_root / project_id

    def _key_prefix_for(self, project_id: str) -> str:
        return f"{self.key_prefix}/{project_id}/"

    def sync_up(self, project_id: str) -> int:
        """Uploads every local file under this project's directory to S3.
        Simple, not incremental (re-uploads unchanged files too) -
        deliberately: this system's projects are mostly small JSON files
        plus a handful of media/render files per project, and "prove
        correctness first, don't optimize" is this deployment's own stated
        priority. Returns the number of files uploaded."""
        local_dir = self._local_dir(project_id)
        if not local_dir.is_dir():
            return 0

        uploaded = 0
        for path in local_dir.rglob("*"):
            if not path.is_file():
                continue
            key = f"{self.key_prefix}/{project_id}/{path.relative_to(local_dir).as_posix()}"
            self.s3.upload_file(str(path), self.bucket, key)
            uploaded += 1
        return uploaded

    def download_all(self, project_id: str) -> int:
        """Downloads every S3 object under this project's key prefix into
        the local directory, overwriting whatever's there - S3 is the
        source of truth on a cold start (a fresh task with empty ephemeral
        disk). Returns the number of files downloaded."""
        local_dir = self._local_dir(project_id)
        prefix = self._key_prefix_for(project_id)

        downloaded = 0
        continuation: Optional[str] = None
        while True:
            kwargs = {"Bucket": self.bucket, "Prefix": prefix}
            if continuation:
                kwargs["ContinuationToken"] = continuation
            response = self.s3.list_objects_v2(**kwargs)

            for obj in response.get("Contents", []):
                key = obj["Key"]
                rel = key[len(prefix):]
                if not rel:
                    continue
                dest = local_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                self.s3.download_file(self.bucket, key, str(dest))
                downloaded += 1

            if response.get("IsTruncated"):
                continuation = response.get("NextContinuationToken")
            else:
                break

        return downloaded

    def exists_in_s3(self, project_id: str) -> bool:
        prefix = self._key_prefix_for(project_id) + "project.json"
        try:
            self.s3.head_object(Bucket=self.bucket, Key=prefix)
            return True
        except Exception:
            return False

    def _etag_marker_path(self, project_id: str) -> Path:
        # Deliberately outside _local_dir(project_id): sync_up() uploads
        # everything under that directory via rglob("*"), and a marker file
        # living inside it would get uploaded to S3 and then downloaded by
        # every *other* task's ensure_local() too - each overwriting the
        # others' freshness bookkeeping with an unrelated value.
        return self.projects_root / f".{project_id}.sync-etag"

    def ensure_local(self, project_id: str) -> None:
        """The read-side counterpart to sync_up: pulls the project down
        from S3 if this task doesn't have the current version cached.

        Originally this only checked "is project.json missing locally",
        which is correct for a cold-start task that has never touched the
        project, but wrong once more than one task can touch the same
        project (this deployment's whole reason for existing - see this
        module's docstring): an API task that merely created a project (and
        so already has *a* local project.json) would never re-sync again
        for that project's lifetime, even after a worker task - on its own
        disk - updated S3 with the actual pipeline results. Found via a
        real staging test run: the API kept serving a project stuck at
        status "CREATED" long after the worker's S3 copy had moved to
        "PACKAGE_READY". Comparing S3's current ETag against the ETag this
        task last synced (not just "do I have *a* copy") is what makes
        ensure_local() correct across tasks instead of only on cold start.
        """
        try:
            remote_etag = self.s3.head_object(
                Bucket=self.bucket, Key=self._key_prefix_for(project_id) + "project.json"
            ).get("ETag")
        except Exception:
            # Nothing in S3 for this project (e.g. a create_project() whose
            # own sync_up hasn't run yet) - nothing to pull down; let the
            # caller's normal not-found handling take it from here based on
            # whatever is (or isn't) already local.
            return

        local_project_json = self._local_dir(project_id) / "project.json"
        etag_marker = self._etag_marker_path(project_id)
        cached_etag = etag_marker.read_text() if etag_marker.is_file() else None

        if local_project_json.is_file() and cached_etag == remote_etag:
            return  # Already have this exact S3 version cached locally.

        downloaded = self.download_all(project_id)
        if downloaded:
            logger.info(f"Synced project {project_id} from S3 ({downloaded} files)")
        if remote_etag is not None:
            etag_marker.write_text(remote_etag)

    def sync_all_project_metadata(self) -> int:
        """Lighter-weight than ensure_local for every project: downloads
        only each project's project.json (not media/renders) so
        list_projects() reflects every project that exists in S3, even
        ones this task has never touched - needed once more than one API
        task can run at once (docs/aws-production-architecture.md §5/§13),
        without pulling potentially large media/render files just to
        populate a listing page."""
        synced = 0
        continuation: Optional[str] = None
        while True:
            kwargs = {"Bucket": self.bucket, "Prefix": f"{self.key_prefix}/", "Delimiter": "/"}
            if continuation:
                kwargs["ContinuationToken"] = continuation
            response = self.s3.list_objects_v2(**kwargs)

            for common_prefix in response.get("CommonPrefixes", []):
                # e.g. "projects/<uuid>/" -> "<uuid>"
                project_id = common_prefix["Prefix"][len(f"{self.key_prefix}/"):].rstrip("/")
                if not project_id:
                    continue
                key = f"{self.key_prefix}/{project_id}/project.json"
                dest = self._local_dir(project_id) / "project.json"
                try:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    self.s3.download_file(self.bucket, key, str(dest))
                    synced += 1
                except Exception as exc:
                    logger.warning(f"Failed to sync metadata for project {project_id}: {exc}")

            if response.get("IsTruncated"):
                continuation = response.get("NextContinuationToken")
            else:
                break

        return synced
