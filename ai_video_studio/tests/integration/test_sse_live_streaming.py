"""Genuine concurrency tests for Milestone W6's SSE endpoints.

Every prior milestone's tests relied on FastAPI's TestClient (or an
in-process httpx.ASGITransport), where a request's BackgroundTasks are
awaited to completion as part of the SAME response cycle before control
ever returns to the caller - there is no real socket in between to let a
client "get its response back" while the server keeps working. This
milestone's actual claims (multiple subscribers seeing the same live
updates, a disconnect not affecting execution) are specifically about that
concurrent, still-in-flight window - so, uniquely among this project's
tests, this file runs the real app on a real socket (uvicorn, in a
background thread of the test process) and drives it with real httpx
clients, the same way a browser or curl genuinely would.
"""
import json
import socket
import threading
import time

import httpx
import uvicorn

from config import settings
from shared_core.contracts.asset_manifest import ValidatedAssetManifest
from web_api import create_app
from web_api.dependencies import get_producer_controller_factory, get_project_manager, get_sse_poll_interval


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _LiveServer:
    def __init__(self, app):
        self.port = _free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self):
        self.thread.start()
        deadline = time.time() + 10
        while not self.server.started and time.time() < deadline:
            time.sleep(0.02)
        if not self.server.started:
            raise RuntimeError("test server did not start in time")
        return self

    def __exit__(self, *exc_info):
        self.server.should_exit = True
        self.thread.join(timeout=10)


def _make_blocking_producer_controller(proceed: threading.Event, entered: threading.Event):
    """A fake ProducerStudioController whose run() blocks on a
    threading.Event the test controls, creating a genuine, observable
    RUNNING window - mark_running() has already fired (producer_runner.py
    calls it before constructing/calling the controller), so a stream
    connecting during this window sees a real, live RUNNING status, not a
    pre-baked one."""
    class _BlockingProducerController:
        def __init__(self, project_manager):
            self.project_manager = project_manager

        def run(self, *, project_id):
            entered.set()
            proceed.wait(timeout=10)
            project = self.project_manager.load_project(project_id)
            manifest = ValidatedAssetManifest(is_valid=True)
            return project, manifest, None, None, None, None, None, None

    return _BlockingProducerController


class _StreamReader(threading.Thread):
    """Reads one client's SSE stream in its own OS thread (httpx's
    streaming read blocks line-by-line), collecting (event_name, payload)
    tuples exactly like web_api/sse.py's own event shape - so assertions
    can compare directly against what run_events() would have yielded."""

    def __init__(self, base_url, run_id, *, stop_after=None):
        super().__init__(daemon=True)
        self.base_url = base_url
        self.run_id = run_id
        self.stop_after = stop_after
        self.events = []
        self.error = None

    def run(self):
        try:
            with httpx.Client(timeout=15.0) as client:
                with client.stream("GET", f"{self.base_url}/runs/{self.run_id}/events") as response:
                    event_name = None
                    for line in response.iter_lines():
                        if line.startswith("event: "):
                            event_name = line[len("event: "):]
                        elif line.startswith("data: "):
                            payload = json.loads(line[len("data: "):])
                            self.events.append((event_name, payload))
                            if self.stop_after is not None and len(self.events) >= self.stop_after:
                                return
        except Exception as exc:  # surfaced to the main thread via .error
            self.error = exc


def test_multiple_subscribers_see_identical_live_updates_and_disconnect_is_safe(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    proceed = threading.Event()
    entered = threading.Event()

    app = create_app()
    app.dependency_overrides[get_producer_controller_factory] = lambda: _make_blocking_producer_controller(
        proceed, entered
    )
    app.dependency_overrides[get_sse_poll_interval] = lambda: 0.05

    with _LiveServer(app) as server:
        project = get_project_manager().create_project()

        with httpx.Client(base_url=server.base_url, timeout=15.0) as client:
            create_response = client.post(f"/projects/{project.project_id}/producer/run")
            assert create_response.status_code == 202
            run_id = create_response.json()["run_id"]

            # Confirms the background task genuinely started (and is
            # genuinely still blocked) before we open any SSE connections -
            # mark_running() has already fired by this point.
            assert entered.wait(timeout=5), "background task never started"

            subscriber_1 = _StreamReader(server.base_url, run_id)
            subscriber_2 = _StreamReader(server.base_url, run_id)
            # Disconnects abruptly after 2 events, while the run is still
            # blocked/running - proves a dropped client doesn't affect
            # execution.
            disconnecting_subscriber = _StreamReader(server.base_url, run_id, stop_after=2)
            for reader in (subscriber_1, subscriber_2, disconnecting_subscriber):
                reader.start()

            # Give the readers a moment to actually connect and receive the
            # RUNNING-transition events before we let the run finish.
            time.sleep(0.5)

            proceed.set()  # let the blocked run finish

            subscriber_1.join(timeout=10)
            subscriber_2.join(timeout=10)
            disconnecting_subscriber.join(timeout=10)

            for reader in (subscriber_1, subscriber_2, disconnecting_subscriber):
                assert reader.error is None, f"subscriber failed: {reader.error}"

            expected_sequence = [
                ("run_started", {"run_id": run_id, "project_id": project.project_id, "type": "producer", "status": "running"}),
                ("stage_changed", {"current_stage": "running"}),
                ("progress", {"progress": 50}),
                ("progress", {"progress": 100}),
                ("completed", {"status": "succeeded"}),
            ]
            assert subscriber_1.events == expected_sequence
            assert subscriber_2.events == expected_sequence
            assert subscriber_1.events == subscriber_2.events  # identical, independently observed
            assert disconnecting_subscriber.events == expected_sequence[:2]

            # The run completed normally despite one subscriber dropping
            # mid-stream - the background task has no coupling to any SSE
            # reader at all.
            run_status = client.get(f"/runs/{run_id}").json()
            assert run_status["status"] == "succeeded"

            # The server itself is unharmed by the abrupt disconnect.
            assert client.get("/health").status_code == 200


def test_project_events_stream_reflects_the_same_live_run(tmp_path, monkeypatch):
    """GET /projects/{id}/events must resolve to and stream the exact same
    live run as GET /runs/{run_id}/events - proven with a real, genuinely
    in-flight run rather than an already-terminal one."""
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    proceed = threading.Event()
    entered = threading.Event()

    app = create_app()
    app.dependency_overrides[get_producer_controller_factory] = lambda: _make_blocking_producer_controller(
        proceed, entered
    )
    app.dependency_overrides[get_sse_poll_interval] = lambda: 0.05

    with _LiveServer(app) as server:
        project = get_project_manager().create_project()

        with httpx.Client(base_url=server.base_url, timeout=15.0) as client:
            create_response = client.post(f"/projects/{project.project_id}/producer/run")
            run_id = create_response.json()["run_id"]
            assert entered.wait(timeout=5)

            class _ProjectStreamReader(_StreamReader):
                def run(self):
                    try:
                        with httpx.Client(timeout=15.0) as client_:
                            with client_.stream("GET", f"{self.base_url}/projects/{project.project_id}/events") as response:
                                event_name = None
                                for line in response.iter_lines():
                                    if line.startswith("event: "):
                                        event_name = line[len("event: "):]
                                    elif line.startswith("data: "):
                                        self.events.append((event_name, json.loads(line[len("data: "):])))
                    except Exception as exc:
                        self.error = exc

            project_reader = _ProjectStreamReader(server.base_url, run_id)
            project_reader.start()
            time.sleep(0.3)
            proceed.set()
            project_reader.join(timeout=10)

            assert project_reader.error is None
            assert project_reader.events[0] == (
                "run_started",
                {"run_id": run_id, "project_id": project.project_id, "type": "producer", "status": "running"},
            )
            assert project_reader.events[-1] == ("completed", {"status": "succeeded"})
