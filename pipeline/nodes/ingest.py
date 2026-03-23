"""
ingest_node — validate and sanitise raw inputs before they enter the pipeline.

Responsibilities:
- Validate JD is not empty / too short
- Truncate JD to 8 000 chars max (before LLMLingua-2 compression)
- Strip null bytes and control characters
- Record Langfuse span
"""

from __future__ import annotations

import re

from pipeline.schemas import GraphState


_MAX_JD_CHARS = 8_000
_MIN_JD_CHARS = 50


def _sanitise(text: str) -> str:
    """Remove null bytes and non-printable control characters (keep newlines/tabs)."""
    # Remove null bytes
    text = text.replace("\x00", "")
    # Remove ASCII control chars except \t, \n, \r
    text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text.strip()


async def ingest_node(state: GraphState) -> GraphState:
    jd = _sanitise(state.jd_raw)

    if len(jd) < _MIN_JD_CHARS:
        return state.model_copy(update={"error": "Job description is too short (< 50 chars)"})

    # Hard cap before LLMLingua compression
    jd = jd[:_MAX_JD_CHARS]

    resume_raw: str | None = None
    if state.resume_raw:
        resume_raw = _sanitise(state.resume_raw)

    return state.model_copy(update={"jd_raw": jd, "resume_raw": resume_raw})
