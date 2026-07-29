from fastapi.testclient import TestClient

from config import settings
from tests.integration.test_pipeline import FakeLLMClient, _happy_path_responses
from web_api import create_app
from web_api.dependencies import get_llm_client_factory
from web_api.run_registry import RunStatus


def test_full_director_pipeline_via_api_succeeds(monkeypatch, tmp_path):
    """End-to-end proof that Milestone W2's async wiring runs the real,
    unmodified DirectorStudioController exactly as app.py does - same
    agents, same sequencing, same ProjectManager persistence - just
    triggered over HTTP instead of argv. Uses the same FakeLLMClient and
    canned happy-path responses as tests/integration/test_pipeline.py so a
    pass here proves the API path produces the same outcome the CLI path
    already does."""
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    fake_llm = FakeLLMClient(_happy_path_responses())
    app = create_app()
    app.dependency_overrides[get_llm_client_factory] = lambda: (lambda: fake_llm)
    client = TestClient(app)

    response = client.post(
        "/projects",
        json={"idea": "A brave explorer", "duration_seconds": 30},
    )
    assert response.status_code == 202
    body = response.json()

    run = client.get(f"/runs/{body['run_id']}").json()
    assert run["status"] == RunStatus.SUCCEEDED.value
    assert run["result"]["shots"]
    assert len(run["result"]["shots"]) == 2

    project = client.get(f"/projects/{body['project_id']}").json()
    assert project["status"] == "PACKAGE_READY"
    assert project["production_package_dir"] is not None


def test_full_director_pipeline_via_api_marks_run_failed_on_real_stage_failure(monkeypatch, tmp_path):
    """A real stage failure (Research Agent gets no canned LLM response)
    drives DirectorStudioController to its real `raise SystemExit(1)` -
    the exact path the API boundary must survive. No mocking of Director
    Studio's failure signal here, unlike the fake-controller unit tests in
    tests/web_api/test_runs.py."""
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    fake_llm = FakeLLMClient([])  # no canned responses - first LLM call fails immediately
    app = create_app()
    app.dependency_overrides[get_llm_client_factory] = lambda: (lambda: fake_llm)
    client = TestClient(app)

    response = client.post("/projects", json={"idea": "A brave explorer", "duration_seconds": 30})
    body = response.json()

    run = client.get(f"/runs/{body['run_id']}").json()
    assert run["status"] == RunStatus.FAILED.value
    assert run["error"] is not None

    project = client.get(f"/projects/{body['project_id']}").json()
    assert project["status"] == "CREATED"

    # The worker survived the real SystemExit(1) and keeps serving requests.
    assert client.get("/health").status_code == 200
