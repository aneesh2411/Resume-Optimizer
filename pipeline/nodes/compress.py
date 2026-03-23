"""
compress_node — compress the job description with LLMLingua-2 before any LLM call.

The compressor is a module-level singleton to avoid re-loading the model on each request.
First call incurs a one-time model-load latency (~3–5 s on CPU); subsequent calls are fast.

Target: reduce JD to ~50% of original token count while preserving key requirement phrases.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from pipeline.schemas import GraphState

if TYPE_CHECKING:
    from llmlingua import PromptCompressor  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# Module-level singleton (loaded lazily on first request)
_compressor: "PromptCompressor | None" = None

# LLMLingua-2 model — multilingual, optimised for meeting-bank style documents
_MODEL_NAME = "microsoft/llmlingua-2-xlm-roberta-large-meetingbank"

# Force-preserve tokens that carry the most signal for resume tailoring
_FORCE_TOKENS = [
    "experience",
    "requirements",
    "skills",
    "responsibilities",
    "qualifications",
    "preferred",
    "required",
]


def _get_compressor() -> "PromptCompressor":
    global _compressor  # noqa: PLW0603
    if _compressor is None:
        try:
            from llmlingua import PromptCompressor  # type: ignore[import-untyped]

            logger.info("Loading LLMLingua-2 model: %s", _MODEL_NAME)
            _compressor = PromptCompressor(
                model_name=_MODEL_NAME,
                use_llmlingua2=True,
                device_map="cpu",
            )
            logger.info("LLMLingua-2 model loaded successfully")
        except Exception as exc:
            logger.error("Failed to load LLMLingua-2: %s — running without compression", exc)
            # Return a no-op compressor so the pipeline can still function
            _compressor = None
    return _compressor  # type: ignore[return-value]


async def compress_node(state: GraphState) -> GraphState:
    """Compress the JD with LLMLingua-2. Skipped on cache hits."""

    if state.cache_hit:
        # Nothing to compress — we already have a cached resume
        return state

    compressor = _get_compressor()

    if compressor is None:
        # Graceful degradation: no compression, pass raw JD through
        logger.warning("LLMLingua-2 unavailable — passing raw JD to generate node")
        return state.model_copy(update={"jd_compressed": state.jd_raw})

    try:
        # LLMLingua-2 compression
        result = compressor.compress_prompt(
            state.jd_raw,
            rate=0.5,               # target 50% token reduction
            force_tokens=_FORCE_TOKENS,
        )
        compressed: str = result["compressed_prompt"]

        logger.debug(
            "JD compressed: %d tokens → %d tokens",
            len(state.jd_raw.split()),
            len(compressed.split()),
        )

        return state.model_copy(update={"jd_compressed": compressed})

    except Exception as exc:
        logger.error("LLMLingua-2 compression failed: %s — using raw JD", exc)
        return state.model_copy(update={"jd_compressed": state.jd_raw})
