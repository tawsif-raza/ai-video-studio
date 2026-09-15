"""AWS deployment prerequisite 3 of 3 (docs/aws-production-architecture.md
§4): the one seam that decides whether a pipeline run executes in-process
(Phase 1.1's PipelineExecutor, today's default) or gets handed to worker.py
via SQS (the target architecture). Every router's own logic - project
creation, run_registry.start_run, the 202 response - is completely
unchanged; only the one background_tasks.add_task(...) call at the end of
each route swaps its target from pipeline_executor.submit directly to this
module's dispatch().

sqs_payload carries only JSON-serializable data (ids, strings, numbers) -
never the project/project_manager/run_registry/controller_factory/
llm_client_factory objects the in-process path uses, since those can't
cross a queue. worker.py reconstructs the equivalent objects itself from
just the stage name and this plain data, then calls the exact same
run_director_pipeline/run_producer_pipeline/run_render_pipeline/
run_publish_pipeline functions (web_api/*_runner.py) the in-process path
already does - those functions themselves needed zero changes for this."""
from __future__ import annotations

import json
from typing import Any, Callable, Dict

from config import settings
from utils.logger import get_logger
from web_api.pipeline_executor import PipelineExecutor
from web_api.run_registry import RunRegistry

logger = get_logger("web_api.pipeline_dispatch")


def dispatch(
    *,
    stage: str,
    run_id: str,
    run_registry: RunRegistry,
    pipeline_executor: PipelineExecutor,
    fn: Callable,
    sqs_payload: Dict[str, Any],
    **fn_kwargs,
) -> None:
    if settings.SQS_QUEUE_URL:
        _enqueue(stage=stage, run_id=run_id, payload=sqs_payload)
    else:
        pipeline_executor.submit(run_id=run_id, run_registry=run_registry, fn=fn, **fn_kwargs)


def _enqueue(*, stage: str, run_id: str, payload: Dict[str, Any]) -> None:
    import boto3

    sqs = boto3.client("sqs", region_name=settings.AWS_REGION or None)
    body = {"stage": stage, "run_id": run_id, **payload}
    sqs.send_message(QueueUrl=settings.SQS_QUEUE_URL, MessageBody=json.dumps(body))
    logger.info(f"Enqueued {stage} run {run_id} to SQS")
