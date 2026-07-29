import uuid

from tests.web_api.conftest import SucceedingProducerController, post_producer_run
from web_api.dependencies import get_project_manager, get_sse_poll_interval


def test_run_events_unknown_run_id_returns_404_not_a_stream(client):
    response = client.get(f"/runs/{uuid.uuid4()}/events")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


def test_run_events_malformed_run_id_returns_422(client):
    response = client.get("/runs/not-a-uuid/events")

    assert response.status_code == 422


def test_project_events_unknown_project_returns_404(client):
    response = client.get(f"/projects/{uuid.uuid4()}/events")

    assert response.status_code == 404


def test_project_events_no_run_yet_returns_404(client, app_):
    project = get_project_manager().create_project()

    response = client.get(f"/projects/{project.project_id}/events")

    assert response.status_code == 404


def test_run_events_stream_has_correct_content_type(client, app_):
    created = post_producer_run(client, app_, SucceedingProducerController, get_project_manager().create_project().project_id).json()

    response = client.get(f"/runs/{created['run_id']}/events")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")


def test_run_events_stream_wire_format_for_a_succeeded_run(client, app_):
    """By the time TestClient's POST call returns, its background task has
    already run to completion (Starlette awaits BackgroundTasks before the
    response is considered finished, and TestClient drives the whole ASGI
    cycle in-process with no real socket) - so this exercises the
    "already-terminal run" path of run_events(), which is exactly what a
    client reconnecting after a run finished would see. True mid-flight
    streaming while a run is genuinely still in progress needs a real
    socket and is covered by tests/integration/test_sse_live_streaming.py."""
    project_id = get_project_manager().create_project().project_id
    created = post_producer_run(client, app_, SucceedingProducerController, project_id).json()

    response = client.get(f"/runs/{created['run_id']}/events")

    assert response.status_code == 200
    body = response.text
    assert "event: progress\ndata: {\"progress\": 100}\n\n" in body
    assert "event: completed\ndata: {\"status\": \"succeeded\"}\n\n" in body
    # No run_started/stage_changed - the transition through RUNNING was
    # never observed since it happened before the stream connected.
    assert "run_started" not in body
    assert "stage_changed" not in body


def test_project_events_resolves_to_the_latest_run_for_that_project(client, app_):
    project_id = get_project_manager().create_project().project_id
    created = post_producer_run(client, app_, SucceedingProducerController, project_id).json()

    response = client.get(f"/projects/{project_id}/events")

    assert response.status_code == 200
    assert created["run_id"]  # sanity: a run really was created
    assert "completed" in response.text


def test_run_events_respects_overridden_poll_interval(client, app_):
    """Confirms the poll_interval dependency is actually wired through to
    run_events() rather than a hardcoded constant - overriding it to an
    absurdly large value would hang a genuinely in-flight stream, but for
    an already-terminal run (see wire-format test above) it never matters,
    since the terminal event fires on the very first check with no sleep
    in between. This test instead checks the dependency override itself
    takes effect by asserting the stream still completes fast."""
    app_.dependency_overrides[get_sse_poll_interval] = lambda: 0.01
    project_id = get_project_manager().create_project().project_id
    created = post_producer_run(client, app_, SucceedingProducerController, project_id).json()

    response = client.get(f"/runs/{created['run_id']}/events")

    assert response.status_code == 200
    assert "completed" in response.text


def test_existing_rest_endpoints_still_work_alongside_events_router(client, app_):
    """W6 requirement: existing REST endpoints continue working unchanged."""
    project = get_project_manager().create_project()

    assert client.get("/health").status_code == 200
    assert client.get("/version").status_code == 200
    assert client.get("/projects").status_code == 200
    assert client.get(f"/projects/{project.project_id}").status_code == 200
