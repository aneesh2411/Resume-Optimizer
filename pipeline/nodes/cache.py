"""
embed_and_cache_node — two-level semantic cache backed by Supabase pgvector.

Level 1: SHA-256 exact hash lookup (zero-cost for identical JDs)
Level 2: text-embedding-3-small cosine similarity ≥ 0.92 (catches paraphrased JDs)

On cache hit:  sets state.cache_hit = True and populates resume_output / critique_results
On cache miss: stores jd_embedding on state for later use in store_cache()
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any

import openai
from supabase import create_client, Client

from pipeline.schemas import CritiqueResult, GraphState, ResumeOutput

logger = logging.getLogger(__name__)

_EMBEDDING_MODEL = "text-embedding-3-small"
_SIMILARITY_THRESHOLD = 0.92


def _get_supabase() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


async def _embed(text: str) -> list[float]:
    """Embed text with OpenAI text-embedding-3-small (1536 dimensions)."""
    client = openai.AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = await client.embeddings.create(model=_EMBEDDING_MODEL, input=text)
    return response.data[0].embedding


async def embed_and_cache_node(state: GraphState) -> GraphState:
    """Check both cache levels. Return cache hit or enriched state for generation."""

    jd_text = state.jd_compressed or state.jd_raw
    jd_hash = hashlib.sha256(jd_text.encode()).hexdigest()

    supabase = _get_supabase()

    # ── Level 1: exact SHA-256 match ──────────────────────────────────────────
    try:
        exact = (
            supabase.table("resume_cache")
            .select("id, resume_output, critique_output")
            .eq("jd_hash", jd_hash)
            .maybe_single()
            .execute()
        )
    except Exception as exc:
        logger.warning("Cache exact-match query failed: %s", exc)
        exact = None

    if exact and exact.data:
        logger.info("Cache hit (exact hash): %s", jd_hash[:16])
        # Bump hit counter (fire-and-forget)
        try:
            supabase.rpc(
                "increment_hit_count", {"row_id": exact.data["id"]}
            ).execute()
        except Exception:
            pass

        critique_raw: list[Any] = exact.data.get("critique_output") or []
        return state.model_copy(
            update={
                "cache_hit": True,
                "jd_hash": jd_hash,
                "resume_output": ResumeOutput(**exact.data["resume_output"]),
                "critique_results": [CritiqueResult(**c) for c in critique_raw],
            }
        )

    # ── Embed (needed for both level-2 search and future cache storage) ───────
    try:
        embedding = await _embed(jd_text)
    except Exception as exc:
        logger.error("Embedding failed: %s — proceeding without cache check", exc)
        return state.model_copy(update={"jd_hash": jd_hash, "cache_hit": False})

    # ── Level 2: semantic similarity search ───────────────────────────────────
    try:
        semantic = supabase.rpc(
            "match_jd_cache",
            {
                "query_embedding": embedding,
                "match_threshold": _SIMILARITY_THRESHOLD,
                "match_count": 1,
            },
        ).execute()
    except Exception as exc:
        logger.warning("Semantic cache query failed: %s", exc)
        semantic = None

    if semantic and semantic.data:
        row = semantic.data[0]
        logger.info(
            "Cache hit (semantic, similarity=%.4f): %s",
            row.get("similarity", 0),
            jd_hash[:16],
        )
        critique_raw = row.get("critique_output") or []
        return state.model_copy(
            update={
                "cache_hit": True,
                "jd_hash": jd_hash,
                "jd_embedding": embedding,
                "resume_output": ResumeOutput(**row["resume_output"]),
                "critique_results": [CritiqueResult(**c) for c in critique_raw],
            }
        )

    logger.info("Cache miss: %s", jd_hash[:16])
    return state.model_copy(
        update={
            "cache_hit": False,
            "jd_hash": jd_hash,
            "jd_embedding": embedding,
        }
    )


async def store_cache(state: GraphState) -> None:
    """
    Persist a successfully generated resume to the cache.
    Called by the FastAPI app after a successful pipeline run (not a graph node).
    """
    if not state.resume_output or not state.jd_hash:
        return

    supabase = _get_supabase()
    jd_text = state.jd_compressed or state.jd_raw

    # Embed if not already done (shouldn't happen normally)
    embedding = state.jd_embedding or await _embed(jd_text)

    critique_json = (
        [c.model_dump(mode="json") for c in state.critique_results]
        if state.critique_results
        else None
    )

    try:
        supabase.table("resume_cache").upsert(
            {
                "jd_hash": state.jd_hash,
                "jd_embedding": embedding,
                "resume_output": state.resume_output.model_dump(mode="json"),
                "critique_output": critique_json,
            },
            on_conflict="jd_hash",
        ).execute()
        logger.info("Stored resume in cache: %s", state.jd_hash[:16])
    except Exception as exc:
        logger.error("Failed to store cache entry: %s", exc)
