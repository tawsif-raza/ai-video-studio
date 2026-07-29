import time

import pytest

from web_api.run_registry import RunConflictError, RunNotFoundError, RunRegistry, RunStatus


def test_start_run_returns_queued_run():
    registry = RunRegistry()

    run = registry.start_run(project_id="p1", stage="director")

    assert run.project_id == "p1"
    assert run.stage == "director"
    assert run.status == RunStatus.QUEUED
    assert run.finished_at is None
    assert run.error is None
    assert run.result is None


def test_start_run_rejects_second_active_run_for_same_project():
    registry = RunRegistry()
    registry.start_run(project_id="p1", stage="director")

    with pytest.raises(RunConflictError):
        registry.start_run(project_id="p1", stage="director")


def test_start_run_allows_different_projects_concurrently():
    registry = RunRegistry()

    first = registry.start_run(project_id="p1", stage="director")
    second = registry.start_run(project_id="p2", stage="director")

    assert first.run_id != second.run_id


def test_mark_running_updates_status():
    registry = RunRegistry()
    run = registry.start_run(project_id="p1", stage="director")

    registry.mark_running(run.run_id)

    assert registry.get(run.run_id).status == RunStatus.RUNNING


def test_mark_succeeded_sets_terminal_state_and_result():
    registry = RunRegistry()
    run = registry.start_run(project_id="p1", stage="director")
    registry.mark_running(run.run_id)

    registry.mark_succeeded(run.run_id, result={"prompt_set_id": "abc"})

    finished = registry.get(run.run_id)
    assert finished.status == RunStatus.SUCCEEDED
    assert finished.finished_at is not None
    assert finished.result == {"prompt_set_id": "abc"}
    assert finished.error is None


def test_mark_failed_sets_terminal_state_and_error():
    registry = RunRegistry()
    run = registry.start_run(project_id="p1", stage="director")

    registry.mark_failed(run.run_id, error="stage exploded")

    finished = registry.get(run.run_id)
    assert finished.status == RunStatus.FAILED
    assert finished.finished_at is not None
    assert finished.error == "stage exploded"


def test_terminal_run_releases_project_lock_for_a_new_run():
    registry = RunRegistry()
    first = registry.start_run(project_id="p1", stage="director")
    registry.mark_succeeded(first.run_id)

    second = registry.start_run(project_id="p1", stage="director")

    assert second.run_id != first.run_id


def test_get_unknown_run_id_raises_run_not_found_error():
    registry = RunRegistry()

    with pytest.raises(RunNotFoundError):
        registry.get("does-not-exist")


def test_get_latest_for_project_returns_the_started_run():
    registry = RunRegistry()
    run = registry.start_run(project_id="p1", stage="render")

    latest = registry.get_latest_for_project("p1", "render")

    assert latest.run_id == run.run_id


def test_get_latest_for_project_unknown_raises_run_not_found_error():
    registry = RunRegistry()

    with pytest.raises(RunNotFoundError):
        registry.get_latest_for_project("p1", "render")


def test_get_latest_for_project_is_scoped_by_stage():
    registry = RunRegistry()
    director_run = registry.start_run(project_id="p1", stage="director")
    registry.mark_succeeded(director_run.run_id)

    with pytest.raises(RunNotFoundError):
        registry.get_latest_for_project("p1", "render")


def test_get_latest_for_project_reflects_most_recent_run_after_completion():
    """Unlike _active_by_project (cleared on completion, so the conflict
    lock only ever reflects genuinely in-flight runs), the latest-run
    pointer must survive completion - GET .../render/status needs to find
    a FINISHED render, not just one that's still running."""
    registry = RunRegistry()
    first = registry.start_run(project_id="p1", stage="render")
    registry.mark_succeeded(first.run_id)

    second = registry.start_run(project_id="p1", stage="render")

    latest = registry.get_latest_for_project("p1", "render")
    assert latest.run_id == second.run_id


def test_get_latest_for_project_any_stage_unknown_raises_run_not_found_error():
    registry = RunRegistry()

    with pytest.raises(RunNotFoundError):
        registry.get_latest_for_project_any_stage("p1")


def test_get_latest_for_project_any_stage_finds_a_run_regardless_of_stage():
    registry = RunRegistry()
    run = registry.start_run(project_id="p1", stage="publish")

    latest = registry.get_latest_for_project_any_stage("p1")

    assert latest.run_id == run.run_id


def test_get_latest_for_project_any_stage_picks_the_most_recently_started_across_stages():
    """A project can have had runs of different stages sequentially over
    its lifetime (director, then later producer, then render, then
    publish) - GET /projects/{id}/events (SS_W6) needs whichever one is
    current, not whichever stage happens to be checked first."""
    registry = RunRegistry()
    director_run = registry.start_run(project_id="p1", stage="director")
    registry.mark_succeeded(director_run.run_id)
    time.sleep(0.001)
    producer_run = registry.start_run(project_id="p1", stage="producer")
    registry.mark_succeeded(producer_run.run_id)
    time.sleep(0.001)
    render_run = registry.start_run(project_id="p1", stage="render")

    latest = registry.get_latest_for_project_any_stage("p1")

    assert latest.run_id == render_run.run_id


def test_get_latest_for_project_any_stage_is_scoped_by_project():
    registry = RunRegistry()
    other_project_run = registry.start_run(project_id="p2", stage="render")

    with pytest.raises(RunNotFoundError):
        registry.get_latest_for_project_any_stage("p1")
