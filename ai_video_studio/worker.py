"""AWS deployment worker entrypoint (docs/aws-production-architecture.md
§4/§9) - the file infra/modules/ecs_worker's task definition runs
(`python worker.py`). Polls the SQS jobs queue and dispatches each message
to the exact same, unmodified run_director_pipeline/run_producer_pipeline/
run_render_pipeline/run_publish_pipeline functions
(web_api/{director,producer,render,publish}_runner.py) the in-process
PipelineExecutor path already calls today - those functions needed zero
changes for this. See web_api/pipeline_dispatch.py for the producer side
of this same seam.

Run directly: `python worker.py`. Requires SQS_QUEUE_URL (config.py) to be
set - refuses to start otherwise, since a worker with nothing to poll is
almost certainly a misconfiguration, not a valid idle state.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

from config import settings
from project_manager.manager import ProjectManager
from utils.logger import get_logger
from web_api.dependencies import (
    get_director_controller_factory,
    get_execution_controller_factory,
    get_llm_client_factory,
    get_producer_controller_factory,
    get_publish_controller_factory,
)
from web_api.director_runner import run_director_pipeline
from web_api.producer_runner import run_producer_pipeline
from web_api.publish_runner import run_publish_pipeline
from web_api.render_runner import run_render_pipeline
from web_api.run_registry import RunRegistry

logger = get_logger("worker")


def build_run_registry():
    """Mirrors web_api/__init__.py's create_app() choice: PostgresRunRegistry
    when DB_HOST is configured (AWS deployment prerequisite 2), otherwise
    the in-memory RunRegistry. A real SQS-enabled deployment always has
    DB_HOST set too (docs/aws-production-architecture.md's prerequisites
    are meant to land together) - the in-memory fallback here exists only
    so this module stays importable/testable without a database, not as a
    supported production configuration (an in-memory registry in the
    worker process would be invisible to the API process's own registry
    instance entirely)."""
    if settings.DB_HOST:
        from db.postgres_run_registry import PostgresRunRegistry

        return PostgresRunRegistry()
    logger.warning("DB_HOST not configured - using in-memory RunRegistry, invisible to the API process's own registry")
    return RunRegistry()


def build_project_manager():
    from storage.s3_syncing_project_manager import build_project_manager as _build

    return _build()


def dispatch_message(body: Dict[str, Any], *, project_manager: ProjectManager, run_registry: RunRegistry) -> None:
    stage = body["stage"]
    run_id = body["run_id"]
    project_id = body["project_id"]

    if stage == "director":
        project = project_manager.load_project(project_id)
        run_director_pipeline(
            run_id=run_id,
            project=project,
            project_manager=project_manager,
            run_registry=run_registry,
            idea=body["idea"],
            duration=body["duration"],
            tone=body.get("tone"),
            audience=body.get("audience"),
            art_style=body.get("art_style"),
            skip_research=body.get("skip_research", False),
            scene_count_mode=body.get("scene_count_mode", "default"),
            scene_count=body.get("scene_count"),
            llm_client_factory=get_llm_client_factory(),
            controller_factory=get_director_controller_factory(),
        )
    elif stage == "producer":
        run_producer_pipeline(
            run_id=run_id,
            project_id=project_id,
            project_manager=project_manager,
            run_registry=run_registry,
            controller_factory=get_producer_controller_factory(),
        )
    elif stage == "render":
        from shared_core.contracts.render import RenderOptions

        options = RenderOptions(**body["options"]) if body.get("options") else RenderOptions()
        run_render_pipeline(
            run_id=run_id,
            project_id=project_id,
            project_manager=project_manager,
            run_registry=run_registry,
            controller_factory=get_execution_controller_factory(),
            options=options,
        )
    elif stage == "publish":
        run_publish_pipeline(
            run_id=run_id,
            project_id=project_id,
            project_manager=project_manager,
            run_registry=run_registry,
            controller_factory=get_publish_controller_factory(),
            platform=body.get("platform", "youtube"),
            dry_run=body.get("dry_run", True),
        )
    else:
        raise ValueError(f"Unknown pipeline stage {stage!r} in message for run {run_id}")


def run_worker_loop(
    *,
    sqs_client,
    queue_url: str,
    project_manager: ProjectManager,
    run_registry: RunRegistry,
    max_iterations: Optional[int] = None,
    poll_wait_seconds: int = 20,
) -> None:
    """The actual poll loop, factored out from main() so it's testable
    against a fake SQS client with a bounded max_iterations - see
    tests/test_worker.py. main() calls this with a real boto3 client and
    max_iterations=None (loop forever)."""
    iterations = 0
    while max_iterations is None or iterations < max_iterations:
        iterations += 1
        response = sqs_client.receive_message(
            QueueUrl=queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=poll_wait_seconds,
        )
        for message in response.get("Messages", []):
            receipt_handle = message["ReceiptHandle"]
            message_id = message.get("MessageId", "?")
            try:
                body = json.loads(message["Body"])
                logger.info(f"Processing message {message_id}: stage={body.get('stage')} run_id={body.get('run_id')}")
                dispatch_message(body, project_manager=project_manager, run_registry=run_registry)
            except Exception:
                # Deliberately do NOT delete the message on failure - it
                # becomes visible again after the queue's visibility
                # timeout and either succeeds on retry or, after
                # max_receive_count attempts, lands in the DLQ
                # (docs/aws-production-architecture.md §7) rather than
                # being silently dropped.
                logger.exception(f"Worker failed to process message {message_id} - leaving it for redelivery/DLQ")
                continue
            sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)


def main() -> None:
    if not settings.SQS_QUEUE_URL:
        raise SystemExit("SQS_QUEUE_URL is not configured - worker.py has nothing to poll (see config.py)")

    import boto3

    sqs = boto3.client("sqs", region_name=settings.AWS_REGION or None)
    project_manager = build_project_manager()
    run_registry = build_run_registry()

    logger.info(f"Worker started - polling {settings.SQS_QUEUE_URL}")
    run_worker_loop(
        sqs_client=sqs,
        queue_url=settings.SQS_QUEUE_URL,
        project_manager=project_manager,
        run_registry=run_registry,
    )


if __name__ == "__main__":
    main()
