"""
cache_and_store_node — final node: persist LaTeX + pdf_url to Supabase.

Upserts on jd_hash so repeated runs don't duplicate rows.
"""

from __future__ import annotations

import logging
import os

from langfuse import Langfuse
from supabase import Client, create_client

from pipeline.schemas import GraphState

logger = logging.getLogger(__name__)


def _get_supabase() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


async def cache_and_store_node(state: GraphState) -> dict:
    """
    Persist the compiled resume to Supabase resume_cache.

    Upserts on jd_hash, so re-running the same JD updates the existing row
    rather than inserting a duplicate.
    """
    lf = Langfuse()
    span = lf.span(
        trace_id=state.get("langfuse_trace_id"),
        name="cache_and_store_node",
        metadata={
            "jd_hash": state.get("jd_hash"),
            "pdf_url": state.get("pdf_url"),
        },
    )

    row: dict = {
        "jd_hash": state.get("jd_hash"),
        "jd_embedding": state.get("jd_embedding"),
        "latex_output": state["latex_output"].model_dump() if state.get("latex_output") else None,
        "pdf_url": state.get("pdf_url"),
        "user_id": state.get("user_id"),  # type: ignore[typeddict-item]
        "critique_output": [c.model_dump() for c in state.get("critique_results", [])],
        "hit_count": 1,
    }

    try:
        supabase = _get_supabase()
        supabase.table("resume_cache").upsert(row, on_conflict="jd_hash").execute()
        logger.info("cache_and_store_node: upserted jd_hash=%s", (state.get("jd_hash") or "")[:16])
    except Exception as exc:
        logger.error("cache_and_store_node: Supabase upsert failed: %s", exc)

    span.end()
    return {}
