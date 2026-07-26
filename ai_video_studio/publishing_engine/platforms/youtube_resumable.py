"""
YouTube/Google's resumable upload protocol (Milestone P7.1):
https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol

Three operations: create a session (one POST that reserves an upload slot
and returns a session URI), upload the file in chunks (a PUT per chunk,
each acknowledged with either "keep going" or the finished video resource),
and query how many bytes the server actually received (an empty-body status
check PUT) - the mechanism that makes resuming after an interruption safe
rather than a guess.

All network calls are constructor-injected so this is fully unit-testable
without a real connection. This module knows nothing about credentials,
visibility, or metadata composition - it receives an already-valid access
token and an already-built request body from its caller (YouTubePlatform).
"""

import requests

from shared_core.contracts.publish import UploadProgress

DEFAULT_CHUNK_SIZE = 8 * 1024 * 1024  # 8 MiB - a multiple of 256 KiB, as Google's docs recommend
RESUMABLE_UPLOAD_ENDPOINT = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"


def _parse_range_upper_bound(range_header):
    """"bytes=0-8388607" -> 8388608 (the number of bytes the server has
    confirmed receiving so far). A missing/malformed header means nothing
    has been received yet."""
    if not range_header:
        return 0
    try:
        return int(range_header.split("-")[1]) + 1
    except (IndexError, ValueError):
        return 0


class YouTubeResumableUpload:
    def __init__(
        self,
        *,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        timeout_seconds: float = 30.0,
        http_post=requests.post,
        http_put=requests.put,
    ):
        self._chunk_size = chunk_size
        self._timeout_seconds = timeout_seconds
        self._http_post = http_post
        self._http_put = http_put

    def create_session(self, *, access_token: str, total_bytes: int, snippet: dict, status: dict):
        """Returns (session_uri, error) - exactly one is None."""
        try:
            response = self._http_post(
                RESUMABLE_UPLOAD_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json; charset=UTF-8",
                    "X-Upload-Content-Type": "video/*",
                    "X-Upload-Content-Length": str(total_bytes),
                },
                json={"snippet": snippet, "status": status},
                timeout=self._timeout_seconds,
            )
        except requests.exceptions.RequestException as e:
            return None, f"network_error: {e}"

        if response.status_code != 200:
            return None, f"session create failed ({response.status_code}): {response.text}"

        location = response.headers.get("Location")
        if not location:
            return None, "session create succeeded but no Location header was returned"
        return location, None

    def query_uploaded_bytes(self, *, session_uri: str, total_bytes: int):
        """Returns (bytes_received, video_id, error) - at most one of
        bytes_received/video_id is set. bytes_received=None with error=None
        means the session is no longer valid (expired/invalid) and the
        caller must start a fresh one, not retry this one."""
        try:
            response = self._http_put(
                session_uri,
                headers={"Content-Range": f"bytes */{total_bytes}", "Content-Length": "0"},
                timeout=self._timeout_seconds,
            )
        except requests.exceptions.RequestException as e:
            return None, None, f"network_error: {e}"

        if response.status_code in (200, 201):
            return total_bytes, response.json().get("id"), None
        if response.status_code == 308:
            return _parse_range_upper_bound(response.headers.get("Range")), None, None
        if response.status_code in (404, 410):
            return None, None, None
        return None, None, f"status check failed ({response.status_code}): {response.text}"

    def upload_chunk(self, *, session_uri: str, chunk: bytes, start: int, total_bytes: int, access_token: str):
        """Uploads exactly one chunk starting at byte `start`. Returns
        (status, next_offset, video_id, error) where status is
        "in_progress" | "completed" | "error"."""
        end = start + len(chunk) - 1
        try:
            response = self._http_put(
                session_uri,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {start}-{end}/{total_bytes}",
                },
                data=chunk,
                timeout=self._timeout_seconds,
            )
        except requests.exceptions.RequestException as e:
            return "error", None, None, f"network_error: {e}"

        if response.status_code == 308:
            return "in_progress", end + 1, None, None
        if response.status_code in (200, 201):
            return "completed", total_bytes, response.json().get("id"), None
        if response.status_code in (404, 410):
            return "error", None, None, "session_expired"
        return "error", None, None, f"chunk upload failed ({response.status_code}): {response.text}"

    def upload_file(
        self,
        *,
        session_uri: str,
        video_path: str,
        total_bytes: int,
        access_token: str,
        resume_from: int = 0,
        progress_callback=None,
        max_resume_attempts: int = 3,
    ):
        """Uploads video_path's bytes to session_uri starting at
        resume_from, chunk by chunk. On an interrupted/ambiguous chunk, asks
        the server for the actual received-byte count and resumes from
        there (bounded to max_resume_attempts before giving up on this
        call) instead of blindly resending or restarting. Returns
        (success, bytes_uploaded, video_id, error) - the caller persists
        bytes_uploaded either way so a later, separate call can resume
        further."""
        offset = resume_from
        resume_attempts = 0
        with open(video_path, "rb") as f:
            while offset < total_bytes:
                f.seek(offset)
                chunk = f.read(self._chunk_size)
                if not chunk:
                    break

                status, next_offset, video_id, error = self.upload_chunk(
                    session_uri=session_uri, chunk=chunk, start=offset, total_bytes=total_bytes,
                    access_token=access_token,
                )

                if status == "error":
                    if error == "session_expired" or resume_attempts >= max_resume_attempts:
                        return False, offset, None, error or "upload interrupted"
                    resume_attempts += 1
                    actual_offset, video_id_from_query, query_error = self.query_uploaded_bytes(
                        session_uri=session_uri, total_bytes=total_bytes
                    )
                    if query_error or actual_offset is None:
                        return False, offset, None, query_error or "session_expired"
                    offset = actual_offset
                    if video_id_from_query:
                        return True, total_bytes, video_id_from_query, None
                    continue

                offset = next_offset
                resume_attempts = 0
                if progress_callback:
                    progress_callback(
                        UploadProgress(
                            bytes_uploaded=offset,
                            total_bytes=total_bytes,
                            percent_complete=round(offset / total_bytes * 100, 2) if total_bytes else 100.0,
                            status="completed" if status == "completed" else "in_progress",
                        )
                    )
                if status == "completed":
                    return True, offset, video_id, None

        return True, offset, None, None
