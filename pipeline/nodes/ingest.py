"""
ingest_node — validate and sanitise raw inputs before they enter the pipeline.

Responsibilities:
- Validate JD is not empty / too short
- Truncate JD to 8 000 chars max (before LLMLingua-2 compression)
- Strip null bytes and control characters
- Validate latex_input contains \\begin{document}
- Validate selected_persona_ids against known persona markdown files
- Record Langfuse span
"""

from __future__ import annotations

import re
from pathlib import Path

from pipeline.schemas import GraphState


_MAX_JD_CHARS = 8_000
_MIN_JD_CHARS = 50

_PERSONAS_DIR = Path(__file__).parent.parent / "personas"


def _sanitise(text: str) -> str:
    """Remove null bytes and non-printable control characters (keep newlines/tabs)."""
    text = text.replace("\x00", "")
    text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text.strip()


def _get_known_persona_ids() -> set[str]:
    """Scan pipeline/personas/*.md and return the set of known persona IDs (stem names)."""
    return {p.stem for p in _PERSONAS_DIR.glob("*.md")}


async def ingest_node(state: GraphState) -> dict:
    jd = _sanitise(state["jd_raw"])[:_MAX_JD_CHARS]

    if len(jd) < _MIN_JD_CHARS:
        return {"error": "Job description is too short (< 50 chars)"}

    latex = _sanitise(state["latex_input"])
    if "\\begin{document}" not in latex:
        return {"error": "latex_input does not appear to be valid LaTeX (missing \\begin{document})"}

    persona_ids: list[str] = state.get("selected_persona_ids", [])
    if not persona_ids:
        return {"error": "At least one persona must be selected"}

    known = _get_known_persona_ids()
    unknown = [p for p in persona_ids if p not in known]
    if unknown:
        return {"error": f"Unknown persona IDs: {unknown}"}

    return {
        "jd_raw": jd,
        "latex_input": latex,
        "selected_persona_ids": persona_ids,
    }
