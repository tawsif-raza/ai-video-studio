import json

from config import settings
from web_api.pipeline_dispatch import dispatch


class FakePipelineExecutor:
    def __init__(self):
        self.submitted = []

    def submit(self, *, run_id, run_registry, fn, **fn_kwargs):
        self.submitted.append({"run_id": run_id, "run_registry": run_registry, "fn": fn, **fn_kwargs})


class FakeSqsClient:
    def __init__(self):
        self.sent = []

    def send_message(self, *, QueueUrl, MessageBody):
        self.sent.append((QueueUrl, json.loads(MessageBody)))


def _fake_fn(**kwargs):
    pass


def test_dispatch_calls_pipeline_executor_when_sqs_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "SQS_QUEUE_URL", "")
    executor = FakePipelineExecutor()

    dispatch(
        stage="director", run_id="r1", run_registry=object(), pipeline_executor=executor,
        fn=_fake_fn, sqs_payload={"project_id": "p1", "idea": "test"},
        project="a-real-project-object", idea="test",
    )

    assert len(executor.submitted) == 1
    assert executor.submitted[0]["run_id"] == "r1"
    assert executor.submitted[0]["fn"] is _fake_fn
    assert executor.submitted[0]["project"] == "a-real-project-object"


def test_dispatch_enqueues_to_sqs_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "SQS_QUEUE_URL", "https://sqs.example/fake-queue")
    fake_sqs = FakeSqsClient()
    monkeypatch.setattr("boto3.client", lambda *a, **kw: fake_sqs)
    executor = FakePipelineExecutor()

    dispatch(
        stage="director", run_id="r1", run_registry=object(), pipeline_executor=executor,
        fn=_fake_fn, sqs_payload={"project_id": "p1", "idea": "test"},
        project="a-real-project-object", idea="test",
    )

    assert executor.submitted == []  # in-process path must NOT also run
    assert len(fake_sqs.sent) == 1
    queue_url, body = fake_sqs.sent[0]
    assert queue_url == "https://sqs.example/fake-queue"
    assert body == {"stage": "director", "run_id": "r1", "project_id": "p1", "idea": "test"}
