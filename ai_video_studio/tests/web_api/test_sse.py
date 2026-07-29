import anyio
import pytest

from web_api.run_registry import RunRegistry
from web_api.sse import run_events

POLL = 0.02  # fast polling for tests - production default lives in web_api.dependencies


def _collect(run_id, run_registry, poll_interval=POLL):
    async def scenario():
        events = []
        async for event in run_events(run_id, run_registry, poll_interval=poll_interval):
            events.append(event)
        return events

    return anyio.run(scenario)


def test_unknown_run_id_yields_no_events():
    registry = RunRegistry()

    events = _collect("does-not-exist", registry)

    assert events == []


def test_already_succeeded_run_yields_only_the_terminal_event():
    """A late subscriber to an already-finished run gets the outcome, not
    a replay of the RUNNING transition it missed - Run carries no
    transition history, only current values."""
    registry = RunRegistry()
    run = registry.start_run(project_id="p1", stage="render")
    registry.mark_succeeded(run.run_id, result={"ok": True})

    events = _collect(run.run_id, registry)

    assert events == [
        ("progress", {"progress": 100}),
        ("completed", {"status": "succeeded"}),
    ]


def test_already_failed_run_yields_only_the_terminal_event():
    registry = RunRegistry()
    run = registry.start_run(project_id="p1", stage="publish")
    registry.mark_failed(run.run_id, error="boom")

    events = _collect(run.run_id, registry)

    assert events == [
        ("progress", {"progress": 100}),
        ("failed", {"status": "failed", "error": "boom"}),
    ]


def test_queued_then_running_then_succeeded_emits_expected_sequence():
    registry = RunRegistry()
    run = registry.start_run(project_id="p1", stage="director")

    async def driver(run_registry, run_id):
        await anyio.sleep(POLL * 2)
        run_registry.mark_running(run_id)
        await anyio.sleep(POLL * 2)
        run_registry.mark_succeeded(run_id, result={"prompt_set_id": "abc"})

    async def scenario():
        events = []
        async with anyio.create_task_group() as tg:
            tg.start_soon(driver, registry, run.run_id)

            async def collect():
                async for event in run_events(run.run_id, registry, poll_interval=POLL):
                    events.append(event)

            tg.start_soon(collect)
        return events

    events = anyio.run(scenario)

    assert events == [
        ("run_started", {
            "run_id": run.run_id, "project_id": "p1", "type": "director", "status": "running",
        }),
        ("stage_changed", {"current_stage": "running"}),
        ("progress", {"progress": 50}),
        ("progress", {"progress": 100}),
        ("completed", {"status": "succeeded"}),
    ]


def test_running_then_failed_emits_expected_sequence():
    registry = RunRegistry()
    run = registry.start_run(project_id="p1", stage="render")

    async def driver(run_registry, run_id):
        await anyio.sleep(POLL * 2)
        run_registry.mark_running(run_id)
        await anyio.sleep(POLL * 2)
        run_registry.mark_failed(run_id, error="ffmpeg not found")

    async def scenario():
        events = []
        async with anyio.create_task_group() as tg:
            tg.start_soon(driver, registry, run.run_id)

            async def collect():
                async for event in run_events(run.run_id, registry, poll_interval=POLL):
                    events.append(event)

            tg.start_soon(collect)
        return events

    events = anyio.run(scenario)

    event_names = [name for name, _ in events]
    assert event_names == ["run_started", "stage_changed", "progress", "progress", "failed"]
    assert events[-1] == ("failed", {"status": "failed", "error": "ffmpeg not found"})


def test_stream_closes_immediately_on_terminal_status_no_further_polling():
    """The generator must return (not keep looping) the instant a terminal
    status is observed - proven by the collected event count staying
    fixed rather than growing if we could keep it running longer."""
    registry = RunRegistry()
    run = registry.start_run(project_id="p1", stage="producer")
    registry.mark_succeeded(run.run_id)

    first_pass = _collect(run.run_id, registry)
    second_pass = _collect(run.run_id, registry)

    assert first_pass == second_pass  # deterministic, not accumulating extra ticks
