"""
compile_node — calls /compile-direct, checks page_count.

If the compiled PDF has more than one page, routes to compress_latex_node.
On compile failure, sets compile_error and routes to END.
"""

from __future__ import annotations

import logging
import os
import uuid

import httpx
from langfuse import Langfuse

from pipeline.models import CompileResult
from pipeline.schemas import GraphState

logger = logging.getLogger(__name__)


async def compile_node(state: GraphState) -> dict:
    """
    POST the current LaTeX to /compile-direct and store the result.

    Uses edited_latex if present (user edit or regex compression),
    otherwise falls back to latex_output.full_latex.
    """
    latex = state.get("edited_latex") or (
        state["latex_output"].full_latex if state.get("latex_output") else ""
    )
    job_id = str(uuid.uuid4())

    lf = Langfuse()
    span = lf.span(
        trace_id=state.get("langfuse_trace_id"),
        name="compile_node",
        metadata={"job_id": job_id},
    )

    pipeline_url = os.environ.get("PIPELINE_URL", "http://localhost:8000")

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            res = await client.post(
                f"{pipeline_url}/compile-direct",
                json={"job_id": job_id, "latex_content": latex, "user_id": "pipeline"},
            )
        res.raise_for_status()
        result = CompileResult(**res.json())
    except Exception as exc:
        logger.error("compile_node HTTP error: %s", exc)
        span.update(metadata={"compile_error": str(exc)})
        span.end()
        return {"compile_error": str(exc), "page_count": 0}

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
