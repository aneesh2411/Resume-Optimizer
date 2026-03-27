"""
critique.py — Send() fan-out: one critique_persona_node invocation per selected persona.

fan_out_to_personas() is used as a conditional edge function from generate_node.
LangGraph calls it and fans out one Send("critique_persona", state) per persona ID.

Each critique_persona_node runs independently (in parallel in LangGraph's async
executor). It returns {"critique_results": [CritiqueResult]}, and LangGraph's
Annotated[list, operator.add] accumulator merges all results into state.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TypedDict

import anthropic
import instructor
from langfuse import Langfuse
from langgraph.types import Send

from pipeline.schemas import CritiqueResult, GraphState

logger = logging.getLogger(__name__)

_PERSONAS_DIR = Path(__file__).parent.parent / "personas"
_MODEL = "claude-haiku-4-5-20251001"

_AI_SLOP_PHRASES = [
    "leveraged synergies",
    "results-driven",
    "dynamic team player",
    "proactively",
    "thought leader",
    "passionate about",
    "spearheaded",
    "drove alignment",
    "cross-functional collaboration",
    "orchestrated",
    "championed",
    "pioneered",
]


class PersonaState(TypedDict, total=False):
    """State slice sent to each critique_persona node via Send()."""

    persona_id: str
    latex_output: object  # LaTeXOutput — avoid circular import in type hint
    jd_compressed: str | None
    jd_raw: str
    latex_analysis: object | None  # LaTeXAnalysis
    langfuse_trace_id: str | None


def _detect_ai_slop(text: str) -> bool:
    """Return True if 3 or more AI slop phrases appear in the text."""
    lower = text.lower()
    hits = sum(1 for phrase in _AI_SLOP_PHRASES if phrase.lower() in lower)
    return hits >= 3


def fan_out_to_personas(state: GraphState) -> list[Send]:
    """Conditional edge function: create one Send per selected persona ID."""
    latex_output = state.get("latex_output")
    return [
        Send(
            "critique_persona",
            {
                "persona_id": pid,
                "latex_output": latex_output,
                "jd_compressed": state.get("jd_compressed"),
                "jd_raw": state["jd_raw"],
                "latex_analysis": state.get("latex_analysis"),
                "langfuse_trace_id": state.get("langfuse_trace_id"),
            },
        )
        for pid in state["selected_persona_ids"]
    ]


async def critique_persona_node(state: PersonaState) -> dict:
    """
    Run a single persona critique. Returns {"critique_results": [CritiqueResult]}.
    The operator.add accumulator in GraphState merges each worker's list.
    """
    persona_id: str = state["persona_id"]

    persona_path = _PERSONAS_DIR / f"{persona_id}.md"
    if not persona_path.exists():
        raise FileNotFoundError(f"Persona markdown not found: {persona_path}")

    persona_prompt = persona_path.read_text(encoding="utf-8")

    latex_output = state.get("latex_output")
    if latex_output is None:
        result = CritiqueResult(
            persona_id=persona_id,
            score=0,
            flags=["No LaTeX output to critique"],
            suggestions=[],
            ai_slop_detected=False,
            jd_match_confidence=0,
        )
        return {"critique_results": [result]}

    latex_text: str = getattr(latex_output, "full_latex", str(latex_output))
    jd = state.get("jd_compressed") or state["jd_raw"]

    lf = Langfuse()
    span = lf.start_observation(
        name=f"critique_{persona_id}",
        metadata={"persona_id": persona_id},
    )

    client = instructor.from_anthropic(
        anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    )

    user_msg = f"""
JOB DESCRIPTION:
{jd}

LATEX RESUME TO EVALUATE:
{latex_text}

Evaluate this resume as described in your persona instructions.
Respond ONLY with the CritiqueResult schema JSON.
Use persona_id="{persona_id}" in your response.
""".strip()

    try:
        result = await client.messages.create(
            model=_MODEL,
            max_tokens=4096,
            system=persona_prompt,
            messages=[{"role": "user", "content": user_msg}],
            response_model=CritiqueResult,
        )
        # Force the persona_id to match the one sent via Send() (LLM might set wrong value)
        result = result.model_copy(update={"persona_id": persona_id})
    except Exception as exc:
        logger.error("Critique persona '%s' failed: %s", persona_id, exc)
        result = CritiqueResult(
            persona_id=persona_id,
            score=0,
            flags=[f"Critique agent error: {exc}"],
            suggestions=[],
            ai_slop_detected=False,
            jd_match_confidence=0,
        )

    # Belt-and-suspenders AI slop check
    ai_slop = result.ai_slop_detected or _detect_ai_slop(latex_text)
    result = result.model_copy(update={"ai_slop_detected": ai_slop})

    span.update(metadata={
        "score": result.score,
        "ai_slop_detected": result.ai_slop_detected,
        "persona_id": persona_id,
    })
    span.end()

    return {"critique_results": [result]}
