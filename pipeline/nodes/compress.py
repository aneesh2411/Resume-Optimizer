"""
compress.py — LLMLingua-2 compressor singleton helper.

The `compress_node` that previously lived here has been removed.
JD compression is now handled inside embed_and_cache_node (nodes/cache.py)
so the hash and embedding are computed on the compressed text.

This module is kept as a helper so other nodes can import _get_compressor().
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from llmlingua import PromptCompressor  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# Module-level singleton (loaded lazily on first request)
_compressor: "PromptCompressor | None" = None

_MODEL_NAME = "microsoft/llmlingua-2-xlm-roberta-large-meetingbank"


def _get_compressor() -> "PromptCompressor | None":
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
            _compressor = None
    return _compressor
