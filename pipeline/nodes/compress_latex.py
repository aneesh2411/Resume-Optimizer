"""
compress_latex_node — regex-only LaTeX compression, no LLM.

Reduces vspace, itemsep, and (on second attempt) font size to push
the document back to a single page. Maximum 2 compression attempts.
If attempts > 2 sets overflow_error = True and routes to END.
"""

from __future__ import annotations

import logging
import re

from langfuse import Langfuse

from pipeline.schemas import GraphState

logger = logging.getLogger(__name__)

_VSPACE_RE = re.compile(r"\\vspace\{[^}]+\}")
_ITEMSEP_RE = re.compile(r"\\itemsep[^\\ ]+")


def _compress(latex: str, attempt: int) -> str:
    """Apply compression passes to latex string."""
    latex = _VSPACE_RE.sub(r"\\vspace{-2pt}", latex)
    latex = _ITEMSEP_RE.sub(r"\\itemsep -1pt ", latex)
    if attempt >= 2:
        latex = latex.replace("\\fontsize{11}", "\\fontsize{10.5}")
        latex = latex.replace("\\fontsize{10}", "\\fontsize{9.5}")
    return latex


async def compress_latex_node(state: GraphState) -> dict:
    """
    Attempt regex compression of current LaTeX to reduce page count.

    Tracks compression_attempts; sets overflow_error after max 2 retries.
    Returns updated edited_latex (or overflow_error=True on exhaustion).
    """
    attempts = (state.get("compression_attempts") or 0) + 1

    lf = Langfuse()
    span = lf.start_observation(
        name="compress_latex_node",
        metadata={"compression_attempts": attempts},
    )
    span.end()

    if attempts > 2:
        logger.warning("compress_latex_node: max compression attempts reached")
        return {"overflow_error": True, "compression_attempts": attempts}

    latex = state.get("edited_latex") or (
        state["latex_output"].full_latex if state.get("latex_output") else ""
    )
    compressed = _compress(latex, attempts)
    logger.info("compress_latex_node: attempt %d, latex len %d → %d", attempts, len(latex), len(compressed))
    return {"edited_latex": compressed, "compression_attempts": attempts}
