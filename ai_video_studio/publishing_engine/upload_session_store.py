"""
Upload session persistence (Milestone P7.1, ARCHITECTURE.md SS24.5). A
resumable-upload session URI is only valid for a limited time and represents
real, already-reserved state on the platform - losing track of it on a
process crash would otherwise mean either abandoning a perfectly resumable
upload or, worse, starting a brand new one and creating a duplicate video.

Stdlib-only, so publishing_engine still depends on nothing beyond
shared_core and itself - no project_manager. The caller supplies the
directory to persist into (typically the project's publishing/ output dir,
exactly like PublishRequest.output_dir already flows from
ProjectManager.get_publish_dir()), the same pattern EnvCredentialProvider
already established for keeping storage decisions outside this package.
"""

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from shared_core.contracts.publish import UploadSession


def fingerprint_video_file(video_path: str) -> str:
    """A cheap, fast fingerprint (size + mtime) of a video file - "avoid
    duplicate uploads where practical", not a cryptographic integrity
    guarantee. Hashing a full multi-hundred-MB video on every upload
    attempt would be slow for little practical benefit: a file's size and
    modification time changing is already a reliable enough signal that
    it's genuinely a different render, and an unchanged size+mtime is a
    reliable enough signal that it's the same one."""
    stat = Path(video_path).stat()
    return f"{stat.st_size}:{stat.st_mtime_ns}"


class UploadSessionStore(ABC):
    """Abstraction over *where* session state is persisted, mirroring
    CredentialProvider's role for credentials - a platform adapter never
    decides a file path or opens a file itself."""

    @abstractmethod
    def load(self, content_fingerprint: str) -> Optional[UploadSession]:
        """Returns the persisted session only if it matches
        content_fingerprint - a session recorded for a different (or
        re-rendered) video is stale and must never be reused."""
        ...

    @abstractmethod
    def save(self, session: UploadSession) -> None:
        ...

    @abstractmethod
    def clear(self) -> None:
        ...


class FileUploadSessionStore(UploadSessionStore):
    """Persists exactly one UploadSession as upload_session.json inside a
    given directory. One file, not one-per-video, because in practice each
    project publishes exactly one video at a time - a session for a
    different video is simply treated as stale (see load())."""

    def __init__(self, session_dir: str):
        self._path = Path(session_dir) / "upload_session.json"

    def load(self, content_fingerprint: str) -> Optional[UploadSession]:
        if not self._path.is_file():
            return None
        try:
            data = json.loads(self._path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        session = UploadSession(**data)
        if session.content_fingerprint != content_fingerprint:
            return None
        return session

    def save(self, session: UploadSession) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(session.model_dump_json(indent=2))

    def clear(self) -> None:
        if self._path.is_file():
            self._path.unlink()
