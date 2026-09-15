import threading

import pytest

from db.postgres_run_registry import PostgresRunRegistry
from web_api.run_registry import RunConflictError, RunNotFoundError, RunStatus


@pytest.fixture
def registry(db_session):
    return PostgresRunRegistry()


def test_start_run_returns_queued_run(registry):
    run = registry.start_run(project_id="p1", stage="director")

    assert run.project_id == "p1"
    assert run.stage == "director"
    assert run.status == RunStatus.QUEUED


def test_start_run_rejects_second_active_run_for_same_project(registry):
    registry.start_run(project_id="p1", stage="director")

    with pytest.raises(RunConflictError):
        registry.start_run(project_id="p1", stage="director")


def test_the_one_active_run_lock_is_enforced_atomically_across_concurrent_callers(registry):
    """The actual guarantee prerequisite 2 exists for
    (docs/aws-production-architecture.md §5): with the in-memory
    RunRegistry, this invariant only holds within one process. Here, N
    threads (standing in for N different API tasks) all race to start a
    run for the SAME project at once - the database's partial unique
    index must let exactly one succeed, not a Python-level lock that
    can't see across processes."""
    results = []
    barrier = threading.Barrier(10)

    def attempt():
        barrier.wait(timeout=5)
        try:
            registry.start_run(project_id="contended-project", stage="director")
            results.append("ok")
        except RunConflictError:
            results.append("conflict")

    threads = [threading.Thread(target=attempt) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert results.count("ok") == 1
    assert results.count("conflict") == 9


def test_start_run_allows_different_projects_concurrently(registry):
    first = registry.start_run(project_id="p1", stage="director")
    second = registry.start_run(project_id="p2", stage="director")

    assert first.run_id != second.run_id


def test_mark_succeeded_sets_terminal_state_and_result(registry):
    run = registry.start_run(project_id="p1", stage="director")
    registry.mark_running(run.run_id)

    registry.mark_succeeded(run.run_id, result={"prompt_set_id": "abc"})

    finished = registry.get(run.run_id)
    assert finished.status == RunStatus.SUCCEEDED
    assert finished.result == {"prompt_set_id": "abc"}


def test_mark_failed_sets_terminal_state_and_error(registry):
    run = registry.start_run(project_id="p1", stage="director")

    registry.mark_failed(run.run_id, error="stage exploded")

    finished = registry.get(run.run_id)
    assert finished.status == RunStatus.FAILED
    assert finished.error == "stage exploded"


def test_terminal_run_releases_project_lock_for_a_new_run(registry):
    first = registry.start_run(project_id="p1", stage="director")
    registry.mark_succeeded(first.run_id)

    second = registry.start_run(project_id="p1", stage="director")

    assert second.run_id != first.run_id


def test_mark_timed_out_and_late_result_is_discarded(registry):
    """Same idempotency guarantee as the in-memory RunRegistry
    (web_api/run_registry.py's _finish, and its own test coverage in
    tests/web_api/test_run_registry.py) - proven here against the real
    database's atomic UPDATE ... WHERE status NOT IN (...) guard."""
    run = registry.start_run(project_id="p1", stage="director")
    registry.mark_running(run.run_id)

    registry.mark_timed_out(run.run_id, timeout_seconds=900)
    registry.mark_succeeded(run.run_id, result={"late": "result"})  # must be a no-op

    finished = registry.get(run.run_id)
    assert finished.status == RunStatus.TIMED_OUT
    assert finished.result is None


def test_get_unknown_run_id_raises(registry):
    with pytest.raises(RunNotFoundError):
        registry.get("does-not-exist")


def test_get_latest_for_project_scoped_by_stage(registry):
    director_run = registry.start_run(project_id="p1", stage="director")
    registry.mark_succeeded(director_run.run_id)

    with pytest.raises(RunNotFoundError):
        registry.get_latest_for_project("p1", "render")

    latest = registry.get_latest_for_project("p1", "director")
    assert latest.run_id == director_run.run_id


def test_get_latest_for_project_any_stage(registry):
    director_run = registry.start_run(project_id="p1", stage="director")
    registry.mark_succeeded(director_run.run_id)
    render_run = registry.start_run(project_id="p1", stage="render")

    latest = registry.get_latest_for_project_any_stage("p1")

    assert latest.run_id == render_run.run_id
