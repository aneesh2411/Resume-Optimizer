"""
compile_node — sends a LaTeX compile job to Azure Service Bus, then
polls Upstash Redis for the result written by the Container App worker.

Routes after returning:
  compile_error set  → END  (surface error to frontend)
  overflow_error set → END  (max compressions reached)
  page_count > 1     → compress_latex_node
  else               → cache_and_store_node
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid

from azure.servicebus.aio import ServiceBusClient
from azure.servicebus import ServiceBusMessage
from langfuse import Langfuse
from upstash_redis.asyncio import Redis as AsyncRedis

from pipeline.models import CompileResult
from pipeline.schemas import GraphState

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 2       # seconds between Redis polls
_MAX_POLLS = 60          # 60 × 2s = 120s max wait


async def compile_node(state: GraphState) -> dict:
    """
    Send the current LaTeX to the compile queue and wait for the result.

    Uses edited_latex if present (user edit or regex compression),
    otherwise falls back to latex_output.full_latex.
    """
    latex = state.get("edited_latex") or (
        state["latex_output"].full_latex if state.get("latex_output") else ""
    )
    job_id = str(uuid.uuid4())

    lf = Langfuse()
    trace_id = state.get("langfuse_trace_id")
    span = lf.start_observation(
        name="compile_node",
        metadata={"job_id": job_id},
        **({"trace_context": {"trace_id": trace_id, "parent_span_id": trace_id}} if trace_id else {}),
    )

    # ── Send job to Service Bus ────────────────────────────────────────────────
    conn_str = os.environ["SERVICEBUS_CONN"]
    queue_name = os.environ["SERVICEBUS_QUEUE"]
    payload = json.dumps({"job_id": job_id, "latex_content": latex, "user_id": "pipeline"})

    try:
        async with ServiceBusClient.from_connection_string(conn_str) as sb_client:
            async with sb_client.get_queue_sender(queue_name=queue_name) as sender:
                await sender.send_messages(ServiceBusMessage(payload))
        logger.info("compile_node: job %s sent to queue '%s'", job_id, queue_name)
    except Exception as exc:
        logger.error("compile_node: Service Bus send failed: %s", exc)
        span.update(metadata={"compile_error": str(exc)})
        span.end()
        return {"compile_error": str(exc), "page_count": 0}

    # ── Poll Redis for result ──────────────────────────────────────────────────
    redis = AsyncRedis(
        url=os.environ["UPSTASH_REDIS_REST_URL"],
        token=os.environ["UPSTASH_REDIS_REST_TOKEN"],
    )
    result_key = f"compile_result:{job_id}"
    result: CompileResult | None = None

    for attempt in range(_MAX_POLLS):
        raw = await redis.get(result_key)
        if raw:
            await redis.delete(result_key)
            result = CompileResult(**json.loads(raw))
            logger.info("compile_node: job %s result received after %ds", job_id, attempt * _POLL_INTERVAL)
            break
        await asyncio.sleep(_POLL_INTERVAL)
    else:
        msg = f"Compile timeout: no result for job {job_id} after {_MAX_POLLS * _POLL_INTERVAL}s"
        logger.error("compile_node: %s", msg)
        span.update(metadata={"compile_error": msg})
        span.end()
        return {"compile_error": msg, "page_count": 0}

    span.update(
        metadata={
            "page_count": result.page_count,
            "compile_error": result.error,
            "success": result.success,
        }
    )
    span.end()

    if not result.success:
        return {"compile_error": result.error or "Unknown compile error", "page_count": 0}

    return {
        "pdf_url": result.pdf_url,
        "page_count": result.page_count,
        "compile_error": None,
    }


def route_after_compile(state: GraphState) -> str:
    """
    Routing after compile_node:
      compile_error set            → END  (surface error to frontend)
      overflow_error set           → END  (max compressions reached)
      page_count > 1               → compress_latex_node
      else                         → cache_and_store_node
    """
    from langgraph.graph import END  # local import avoids circular

    if state.get("compile_error"):
        return END
    if state.get("overflow_error"):
        return END
    if (state.get("page_count") or 0) > 1:
        return "compress_latex_node"
    return "cache_and_store_node"
