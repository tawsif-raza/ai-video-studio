"""Tests worker.py's own logic - message routing/kwarg-mapping
(dispatch_message) and the poll loop's failure handling (run_worker_loop) -
against fakes. The four run_*_pipeline functions themselves are already
covered by tests/web_api/test_{runs,producer,render,publish}.py and the
tests/integration/test_api_*_pipeline.py suite; re-testing them here would
just be duplicate coverage of code this file doesn't modify."""
import json

import pytest

import worker
from config import settings
from project_manager.manager import ProjectManager


class FakeSqsClient:
    def __init__(self, messages):
        # Each item: (message_id, receipt_handle, body_dict)
        self._queue = list(messages)
        self.deleted_receipt_handles = []

    def receive_message(self, **kwargs):
        if not self._queue:
            return {"Messages": []}
        message_id, receipt_handle, body = self._queue.pop(0)
        return {"Messages": [{"MessageId": message_id, "ReceiptHandle": receipt_handle, "Body": json.dumps(body)}]}

    def delete_message(self, *, QueueUrl, ReceiptHandle):
        self.deleted_receipt_handles.append(ReceiptHandle)


@pytest.fixture
def project_manager(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    return ProjectManager()


def test_dispatch_message_director_stage(monkeypatch, project_manager):
    project = project_manager.create_project()
    calls = []

    def fake_run_director_pipeline(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(worker, "run_director_pipeline", fake_run_director_pipeline)

    worker.dispatch_message(
        {
            "stage": "director", "run_id": "r1", "project_id": project.project_id,
            "idea": "A brave explorer", "duration": 30, "tone": "epic", "audience": None,
            "art_style": None, "skip_research": True, "scene_count_mode": "custom", "scene_count": 5,
        },
        project_manager=project_manager,
        run_registry=object(),
    )

    assert len(calls) == 1
    call = calls[0]
    assert call["run_id"] == "r1"
    assert call["project"].project_id == project.project_id
    assert call["idea"] == "A brave explorer"
    assert call["duration"] == 30
    assert call["tone"] == "epic"
    assert call["skip_research"] is True
    assert call["scene_count_mode"] == "custom"
    assert call["scene_count"] == 5
    assert callable(call["llm_client_factory"])
    assert callable(call["controller_factory"])


def test_dispatch_message_producer_stage(monkeypatch, project_manager):
    calls = []
    monkeypatch.setattr(worker, "run_producer_pipeline", lambda **kw: calls.append(kw))

    worker.dispatch_message(
        {"stage": "producer", "run_id": "r2", "project_id": "p2"},
        project_manager=project_manager,
        run_registry=object(),
    )

    assert calls[0]["run_id"] == "r2"
    assert calls[0]["project_id"] == "p2"


def test_dispatch_message_render_stage_reconstructs_render_options(monkeypatch, project_manager):
    calls = []
    monkeypatch.setattr(worker, "run_render_pipeline", lambda **kw: calls.append(kw))

    worker.dispatch_message(
        {
            "stage": "render", "run_id": "r3", "project_id": "p3",
            "options": {"resolution": "1920x1080", "fps": 30, "timeout_seconds": 60},
        },
        project_manager=project_manager,
        run_registry=object(),
    )

    assert calls[0]["options"].resolution == "1920x1080"
    assert calls[0]["options"].timeout_seconds == 60


def test_dispatch_message_render_stage_defaults_options_when_absent(monkeypatch, project_manager):
    calls = []
    monkeypatch.setattr(worker, "run_render_pipeline", lambda **kw: calls.append(kw))

    worker.dispatch_message(
        {"stage": "render", "run_id": "r4", "project_id": "p4"},
        project_manager=project_manager,
        run_registry=object(),
    )

    assert calls[0]["options"].timeout_seconds == 120  # RenderOptions' own default


def test_dispatch_message_publish_stage(monkeypatch, project_manager):
    calls = []
    monkeypatch.setattr(worker, "run_publish_pipeline", lambda **kw: calls.append(kw))

    worker.dispatch_message(
        {"stage": "publish", "run_id": "r5", "project_id": "p5", "platform": "youtube", "dry_run": False},
        project_manager=project_manager,
        run_registry=object(),
    )

    assert calls[0]["platform"] == "youtube"
    assert calls[0]["dry_run"] is False


def test_dispatch_message_unknown_stage_raises(project_manager):
    with pytest.raises(ValueError, match="Unknown pipeline stage"):
        worker.dispatch_message(
            {"stage": "not-a-real-stage", "run_id": "r6", "project_id": "p6"},
            project_manager=project_manager,
            run_registry=object(),
        )


def test_run_worker_loop_deletes_message_on_success(monkeypatch, project_manager):
    monkeypatch.setattr(worker, "dispatch_message", lambda body, **kw: None)
    sqs = FakeSqsClient([("m1", "receipt-1", {"stage": "producer", "run_id": "r1", "project_id": "p1"})])

    worker.run_worker_loop(
        sqs_client=sqs, queue_url="fake-queue-url",
        project_manager=project_manager, run_registry=object(),
        max_iterations=1, poll_wait_seconds=0,
    )

    assert sqs.deleted_receipt_handles == ["receipt-1"]


def test_run_worker_loop_leaves_message_undeleted_on_failure(monkeypatch, project_manager):
    def _boom(body, **kw):
        raise RuntimeError("simulated pipeline crash")

    monkeypatch.setattr(worker, "dispatch_message", _boom)
    sqs = FakeSqsClient([("m1", "receipt-1", {"stage": "producer", "run_id": "r1", "project_id": "p1"})])

    worker.run_worker_loop(
        sqs_client=sqs, queue_url="fake-queue-url",
        project_manager=project_manager, run_registry=object(),
        max_iterations=1, poll_wait_seconds=0,
    )

    # Not deleted - left for SQS redelivery / eventual DLQ, per
    # docs/aws-production-architecture.md §7. Confirms a crash in one
    # message's processing doesn't crash the worker loop itself either.
    assert sqs.deleted_receipt_handles == []


def test_run_worker_loop_stops_after_max_iterations_with_no_messages(project_manager):
    sqs = FakeSqsClient([])  # never has anything

    worker.run_worker_loop(
        sqs_client=sqs, queue_url="fake-queue-url",
        project_manager=project_manager, run_registry=object(),
        max_iterations=3, poll_wait_seconds=0,
    )
    # No assertion beyond "this returns" - proves the loop is genuinely
    # bounded by max_iterations rather than looping forever when idle.


def test_main_refuses_to_start_without_sqs_queue_url(monkeypatch):
    monkeypatch.setattr(settings, "SQS_QUEUE_URL", "")

    with pytest.raises(SystemExit, match="SQS_QUEUE_URL is not configured"):
        worker.main()
