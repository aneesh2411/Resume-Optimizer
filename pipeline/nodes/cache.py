"""
embed_and_cache_node — two-level semantic cache backed by Supabase pgvector.

Level 1: SHA-256 exact hash lookup (zero-cost for identical JDs)
Level 2: text-embedding-3-small cosine similarity ≥ 0.92 (catches paraphrased JDs)

JD compression (LLMLingua-2) is performed here before hash computation so that
the hash and embedding are based on the compressed text (stable signal).

On cache hit:  returns {"cache_hit": True, "jd_hash": ..., "pdf_url": ..., "latex_output": ...}
On cache miss: returns {"cache_hit": False, "jd_hash": ..., "jd_embedding": ..., "jd_compressed": ...}
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any

import openai
from supabase import create_client, Client

from pipeline.nodes.compress import _get_compressor
from pipeline.schemas import CritiqueResult, GraphState, LaTeXOutput

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


def _compress_jd(jd_raw: str) -> str:
    """Run LLMLingua-2 compression on the JD; fall back to raw JD on failure."""
    compressor = _get_compressor()
    if compressor is None:
        logger.warning("LLMLingua-2 unavailable — using raw JD for hash/embedding")
        return jd_raw
    try:
        result = compressor.compress_prompt(
            jd_raw,
            rate=0.5,
            force_tokens=["experience", "requirements", "skills",
                          "responsibilities", "qualifications", "preferred", "required"],
        )
        compressed: str = result["compressed_prompt"]
        logger.debug(
            "JD compressed: %d → %d words",
            len(jd_raw.split()),
            len(compressed.split()),
        )
        return compressed
    except Exception as exc:
        logger.error("LLMLingua-2 compression failed: %s — using raw JD", exc)
        return jd_raw


async def embed_and_cache_node(state: GraphState) -> dict:
    """Check both cache levels. Return cache hit (with pdf_url) or miss for generation."""

    # Compress JD before hash so identical-meaning JDs share a cache entry
    compressed_jd = _compress_jd(state["jd_raw"])
    jd_hash = hashlib.sha256(compressed_jd.encode()).hexdigest()

    supabase = _get_supabase()

    # ── Level 1: exact SHA-256 match ──────────────────────────────────────────
    try:
        exact = (
            supabase.table("resume_cache")
            .select("id, latex_output, critique_output, pdf_url")
            .eq("jd_hash", jd_hash)
            .maybe_single()
            .execute()
        )
    except Exception as exc:
        logger.warning("Cache exact-match query failed: %s", exc)
        exact = None

    if exact and exact.data:
        row = exact.data
        logger.info("Cache hit (exact hash): %s", jd_hash[:16])
        try:
            supabase.rpc("increment_hit_count", {"row_id": row["id"]}).execute()
        except Exception:
            pass

        latex_output: LaTeXOutput | None = None
        if row.get("latex_output"):
            try:
                latex_output = LaTeXOutput(**row["latex_output"])
            except Exception:
                pass

        return {
            "cache_hit": True,
            "jd_hash": jd_hash,
            "jd_compressed": compressed_jd,
            "pdf_url": row.get("pdf_url"),
            "latex_output": latex_output,
        }

    # ── Embed (needed for both level-2 search and future cache storage) ───────
    try:
        embedding = await _embed(compressed_jd)
    except Exception as exc:
        logger.error("Embedding failed: %s — proceeding without cache check", exc)
        return {
            "cache_hit": False,
            "jd_hash": jd_hash,
            "jd_compressed": compressed_jd,
        }

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

        latex_output = None
        if row.get("latex_output"):
            try:
                latex_output = LaTeXOutput(**row["latex_output"])
            except Exception:
                pass

        return {
            "cache_hit": True,
            "jd_hash": jd_hash,
            "jd_compressed": compressed_jd,
            "jd_embedding": embedding,
            "pdf_url": row.get("pdf_url"),
            "latex_output": latex_output,
        }

    logger.info("Cache miss: %s", jd_hash[:16])
    return {
        "cache_hit": False,
        "jd_hash": jd_hash,
        "jd_compressed": compressed_jd,
        "jd_embedding": embedding,
    }
