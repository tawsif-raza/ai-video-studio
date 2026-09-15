"""The integration seam that actually wires S3ProjectSync into the app -
see s3_project_sync.py's module docstring for why this is a wrapper
rather than a rewrite of ProjectManager itself.

S3SyncingProjectManager forwards every attribute access to a real,
unmodified ProjectManager via __getattr__, wrapping each *method* (not
plain attributes) with a before/after hook chosen generically from the
method's name - "load_*"/"get_*"/"scan_media" sync the project down from
S3 first if it's not already cached on this task's local disk; "save_*"/
"export_*"/"delete_*"/"create_project" sync it up to S3 afterward.
Deliberately generic (name-prefix-based) rather than one hand-written
wrapper per method: ProjectManager has ~60 public methods
(project_manager/manager.py), and a per-method list would be exactly the
kind of thing that silently goes stale the next time a save_* method is
added - matching a prefix pattern can't drift out of sync with the class
it wraps.

Only ever constructed when S3_BUCKET_NAME is configured
(web_api/dependencies.py::get_project_manager) - local development, the
CLIs (app.py/producer_app.py/render_app.py/publish_app.py), and the
entire existing test suite construct a plain ProjectManager() with no
wrapper at all, so none of their behavior changes because this file
exists.
"""
from __future__ import annotations

import functools
from typing import Any

from project_manager.manager import ProjectManager
from storage.s3_project_sync import S3ProjectSync
from utils.logger import get_logger

logger = get_logger("storage.s3_syncing_project_manager")

_WRITE_PREFIXES = ("save_", "export_", "delete_")
_WRITE_EXACT = {"create_project"}
_READ_PREFIXES = ("load_", "get_media", "get_images", "get_render", "get_publish")
_READ_EXACT = {"scan_media"}
_LIST_EXACT = {"list_projects"}


def _extract_project_id(args: tuple, kwargs: dict) -> Any:
    """ProjectManager's own methods are consistent about this (verified
    against every method in project_manager/manager.py that's actually
    called from web_api/ - see storage/s3_project_sync.py's module
    docstring): the identifying argument is always either the first
    positional argument or a `project`/`project_id` keyword, and it's
    either a plain project_id string or a Project object with a
    .project_id attribute."""
    candidate = None
    if args:
        candidate = args[0]
    elif "project" in kwargs:
        candidate = kwargs["project"]
    elif "project_id" in kwargs:
        candidate = kwargs["project_id"]

    if candidate is None:
        return None
    if isinstance(candidate, str):
        return candidate
    return getattr(candidate, "project_id", None)


def build_project_manager():
    """Factory used by web_api/dependencies.py::get_project_manager.
    Returns a plain, unmodified ProjectManager when S3_BUCKET_NAME isn't
    configured (local dev, the CLIs, and the entire existing test suite -
    zero behavior change), or an S3SyncingProjectManager wrapping one when
    it is (the AWS deployment)."""
    delegate = ProjectManager()

    from config import settings

    if not settings.S3_BUCKET_NAME:
        return delegate

    import boto3

    s3_client = boto3.client("s3", region_name=settings.AWS_REGION or None)
    sync = S3ProjectSync(
        bucket=settings.S3_BUCKET_NAME,
        s3_client=s3_client,
        projects_root=settings.OUTPUT_DIR / "projects",
    )
    logger.info(f"S3 project sync enabled - bucket={settings.S3_BUCKET_NAME}")
    return S3SyncingProjectManager(delegate, sync)


class S3SyncingProjectManager:
    def __init__(self, delegate: ProjectManager, sync: S3ProjectSync):
        self._delegate = delegate
        self._sync = sync

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._delegate, name)
        if not callable(attr):
            return attr

        if name in _LIST_EXACT:
            return self._wrap_list(attr)
        if name in _READ_EXACT or name.startswith(_READ_PREFIXES):
            return self._wrap_read(name, attr)
        if name in _WRITE_EXACT or name.startswith(_WRITE_PREFIXES):
            return self._wrap_write(name, attr)
        # Private helpers (_project_dir, _write_project_file, etc.) and
        # anything else not shaped like a project-scoped read/write pass
        # straight through, unwrapped.
        return attr

    def _wrap_read(self, name: str, method):
        @functools.wraps(method)
        def wrapped(*args, **kwargs):
            project_id = _extract_project_id(args, kwargs)
            if project_id:
                try:
                    self._sync.ensure_local(project_id)
                except Exception as exc:
                    # A sync-down failure should surface as "project not
                    # found" through the normal, already-handled path
                    # (load_project already raises FileNotFoundError for a
                    # missing local dir) - not a new, unhandled exception
                    # shape callers don't already expect.
                    logger.warning(f"S3 sync-down failed for project {project_id} before {name}(): {exc}")
            return method(*args, **kwargs)

        return wrapped

    def _wrap_write(self, name: str, method):
        @functools.wraps(method)
        def wrapped(*args, **kwargs):
            result = method(*args, **kwargs)
            project_id = _extract_project_id(args, kwargs)
            if project_id is None and name == "create_project":
                project_id = getattr(result, "project_id", None)
            if project_id:
                try:
                    self._sync.sync_up(project_id)
                except Exception as exc:
                    # Deliberately does not fail the request: the write
                    # already succeeded on local disk (this task can keep
                    # serving it), and a transient S3 error shouldn't turn
                    # a successful save into a 500. It does mean this
                    # project's durability is at risk until the next
                    # successful sync - logged loudly so it's visible in
                    # CloudWatch, not silently swallowed.
                    logger.error(f"S3 sync-up FAILED for project {project_id} after {name}() - data at risk on task restart: {exc}")
            return result

        return wrapped

    def _wrap_list(self, method):
        @functools.wraps(method)
        def wrapped(*args, **kwargs):
            try:
                self._sync.sync_all_project_metadata()
            except Exception as exc:
                logger.warning(f"S3 metadata sync failed before list_projects(): {exc}")
            return method(*args, **kwargs)

        return wrapped
