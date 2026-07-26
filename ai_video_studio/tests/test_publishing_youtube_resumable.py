import requests

from publishing_engine.platforms.youtube_resumable import YouTubeResumableUpload


class _FakeResponse:
    def __init__(self, status_code=200, headers=None, json_data=None, text=""):
        self.status_code = status_code
        self.headers = headers or {}
        self._json_data = json_data if json_data is not None else {}
        self.text = text

    def json(self):
        return self._json_data


def _scripted(responses):
    it = iter(responses)

    def fn(*args, **kwargs):
        item = next(it)
        if isinstance(item, Exception):
            raise item
        return item

    return fn


# ---- create_session ----


def test_create_session_returns_location_header_on_success():
    uploader = YouTubeResumableUpload(
        http_post=_scripted([_FakeResponse(status_code=200, headers={"Location": "https://upload.example/session/1"})])
    )

    uri, error = uploader.create_session(
        access_token="tok", total_bytes=1000, snippet={"title": "T"}, status={"privacyStatus": "private"}
    )

    assert uri == "https://upload.example/session/1"
    assert error is None


def test_create_session_fails_on_non_200():
    uploader = YouTubeResumableUpload(http_post=_scripted([_FakeResponse(status_code=400, text="bad request")]))

    uri, error = uploader.create_session(access_token="tok", total_bytes=1000, snippet={}, status={})

    assert uri is None
    assert "400" in error


def test_create_session_fails_when_location_header_missing():
    uploader = YouTubeResumableUpload(http_post=_scripted([_FakeResponse(status_code=200, headers={})]))

    uri, error = uploader.create_session(access_token="tok", total_bytes=1000, snippet={}, status={})

    assert uri is None
    assert "Location" in error


def test_create_session_handles_network_error():
    uploader = YouTubeResumableUpload(http_post=_scripted([requests.exceptions.ConnectionError("no network")]))

    uri, error = uploader.create_session(access_token="tok", total_bytes=1000, snippet={}, status={})

    assert uri is None
    assert "network_error" in error


# ---- query_uploaded_bytes ----


def test_query_uploaded_bytes_parses_range_header():
    uploader = YouTubeResumableUpload(
        http_put=_scripted([_FakeResponse(status_code=308, headers={"Range": "bytes=0-8388607"})])
    )

    bytes_received, video_id, error = uploader.query_uploaded_bytes(session_uri="uri", total_bytes=10_000_000)

    assert bytes_received == 8388608
    assert video_id is None
    assert error is None


def test_query_uploaded_bytes_when_already_complete():
    uploader = YouTubeResumableUpload(
        http_put=_scripted([_FakeResponse(status_code=200, json_data={"id": "vid123"})])
    )

    bytes_received, video_id, error = uploader.query_uploaded_bytes(session_uri="uri", total_bytes=1000)

    assert bytes_received == 1000
    assert video_id == "vid123"


def test_query_uploaded_bytes_returns_none_for_expired_session():
    uploader = YouTubeResumableUpload(http_put=_scripted([_FakeResponse(status_code=404)]))

    bytes_received, video_id, error = uploader.query_uploaded_bytes(session_uri="uri", total_bytes=1000)

    assert bytes_received is None
    assert video_id is None
    assert error is None  # expired is not an error - caller starts a fresh session


def test_query_uploaded_bytes_handles_network_error():
    uploader = YouTubeResumableUpload(http_put=_scripted([requests.exceptions.Timeout("timed out")]))

    bytes_received, video_id, error = uploader.query_uploaded_bytes(session_uri="uri", total_bytes=1000)

    assert bytes_received is None
    assert "network_error" in error


# ---- upload_chunk ----


def test_upload_chunk_in_progress_returns_next_offset():
    uploader = YouTubeResumableUpload(
        http_put=_scripted([_FakeResponse(status_code=308)])
    )

    status, next_offset, video_id, error = uploader.upload_chunk(
        session_uri="uri", chunk=b"0123456789", start=0, total_bytes=100, access_token="tok"
    )

    assert status == "in_progress"
    assert next_offset == 10
    assert video_id is None


def test_upload_chunk_completed_returns_video_id():
    uploader = YouTubeResumableUpload(
        http_put=_scripted([_FakeResponse(status_code=200, json_data={"id": "vidXYZ"})])
    )

    status, next_offset, video_id, error = uploader.upload_chunk(
        session_uri="uri", chunk=b"0123456789", start=90, total_bytes=100, access_token="tok"
    )

    assert status == "completed"
    assert next_offset == 100
    assert video_id == "vidXYZ"


def test_upload_chunk_reports_session_expired():
    uploader = YouTubeResumableUpload(http_put=_scripted([_FakeResponse(status_code=404)]))

    status, next_offset, video_id, error = uploader.upload_chunk(
        session_uri="uri", chunk=b"data", start=0, total_bytes=100, access_token="tok"
    )

    assert status == "error"
    assert error == "session_expired"


def test_upload_chunk_handles_network_error():
    uploader = YouTubeResumableUpload(http_put=_scripted([requests.exceptions.ConnectionError("dropped")]))

    status, next_offset, video_id, error = uploader.upload_chunk(
        session_uri="uri", chunk=b"data", start=0, total_bytes=100, access_token="tok"
    )

    assert status == "error"
    assert "network_error" in error


# ---- upload_file (full orchestration) ----


def test_upload_file_completes_in_a_single_chunk(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x" * 20)
    uploader = YouTubeResumableUpload(
        chunk_size=100,  # bigger than the file - one chunk covers everything
        http_put=_scripted([_FakeResponse(status_code=200, json_data={"id": "vid1"})]),
    )
    progress_events = []

    success, bytes_uploaded, video_id, error = uploader.upload_file(
        session_uri="uri", video_path=str(video), total_bytes=20, access_token="tok",
        progress_callback=progress_events.append,
    )

    assert success is True
    assert bytes_uploaded == 20
    assert video_id == "vid1"
    assert len(progress_events) == 1
    assert progress_events[0].status == "completed"
    assert progress_events[0].percent_complete == 100.0


def test_upload_file_uploads_multiple_chunks_and_reports_progress(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x" * 25)
    uploader = YouTubeResumableUpload(
        chunk_size=10,  # forces 3 chunks: 10, 10, 5
        http_put=_scripted(
            [
                _FakeResponse(status_code=308),
                _FakeResponse(status_code=308),
                _FakeResponse(status_code=200, json_data={"id": "vid2"}),
            ]
        ),
    )
    progress_events = []

    success, bytes_uploaded, video_id, error = uploader.upload_file(
        session_uri="uri", video_path=str(video), total_bytes=25, access_token="tok",
        progress_callback=progress_events.append,
    )

    assert success is True
    assert bytes_uploaded == 25
    assert video_id == "vid2"
    assert [e.bytes_uploaded for e in progress_events] == [10, 20, 25]
    assert [e.status for e in progress_events] == ["in_progress", "in_progress", "completed"]


def test_upload_file_resumes_after_a_transient_network_error(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x" * 25)
    uploader = YouTubeResumableUpload(
        chunk_size=10,
        http_put=_scripted(
            [
                requests.exceptions.ConnectionError("dropped mid-chunk"),  # first chunk attempt fails
                _FakeResponse(status_code=308, headers={"Range": "bytes=0-9"}),  # query: 10 bytes actually received
                _FakeResponse(status_code=308),  # second chunk (bytes 10-19)
                _FakeResponse(status_code=200, json_data={"id": "vid3"}),  # final chunk
            ]
        ),
    )

    success, bytes_uploaded, video_id, error = uploader.upload_file(
        session_uri="uri", video_path=str(video), total_bytes=25, access_token="tok",
    )

    assert success is True
    assert bytes_uploaded == 25
    assert video_id == "vid3"


def test_upload_file_gives_up_after_exceeding_max_resume_attempts(tmp_path):
    # Each failed chunk PUT is followed by a *successful* status-check query
    # (so the loop genuinely retries rather than failing on the query
    # itself) - this exercises the resume_attempts counter reaching
    # max_resume_attempts=2 and giving up, not merely "the very first query
    # also failed" (a different, already-covered code path).
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x" * 10)
    uploader = YouTubeResumableUpload(
        chunk_size=10,
        http_put=_scripted(
            [
                requests.exceptions.ConnectionError("down 1"),
                _FakeResponse(status_code=308, headers={"Range": "bytes=0-4"}),  # query succeeds, offset=5
                requests.exceptions.ConnectionError("down 2"),
                _FakeResponse(status_code=308, headers={"Range": "bytes=0-4"}),  # query succeeds again
                requests.exceptions.ConnectionError("down 3"),  # 3rd failure - resume_attempts(2) >= max(2), give up
            ]
        ),
    )

    success, bytes_uploaded, video_id, error = uploader.upload_file(
        session_uri="uri", video_path=str(video), total_bytes=10, access_token="tok", max_resume_attempts=2,
    )

    assert success is False
    assert video_id is None
    assert "down 3" in error


def test_upload_file_stops_immediately_on_session_expired(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x" * 10)
    uploader = YouTubeResumableUpload(chunk_size=10, http_put=_scripted([_FakeResponse(status_code=404)]))

    success, bytes_uploaded, video_id, error = uploader.upload_file(
        session_uri="uri", video_path=str(video), total_bytes=10, access_token="tok",
    )

    assert success is False
    assert error == "session_expired"


def test_upload_file_resumes_from_a_nonzero_offset(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x" * 20)
    uploader = YouTubeResumableUpload(
        chunk_size=10,
        http_put=_scripted([_FakeResponse(status_code=200, json_data={"id": "vid4"})]),
    )

    success, bytes_uploaded, video_id, error = uploader.upload_file(
        session_uri="uri", video_path=str(video), total_bytes=20, access_token="tok", resume_from=10,
    )

    assert success is True
    assert bytes_uploaded == 20
    assert video_id == "vid4"
