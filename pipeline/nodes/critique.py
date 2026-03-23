"""
parallel_critique_node — fan out to three simultaneous critique agents.

Uses asyncio.gather to run recruiter, hiring_manager, and expert critiques
in parallel. Each agent loads its persona from /personas/<name>.md and
returns a CritiqueResult via Instructor.

Guardrails AI slop detection is also applied here as a post-processing step.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import anthropic
import instructor
from langfuse import Langfuse

from pipeline.schemas import CritiqueResult, GraphState

logger = logging.getLogger(__name__)

_PERSONAS_DIR = Path(__file__).parent.parent / "personas"
_MODEL = "claude-sonnet-4-6"

# Phrases that signal AI-generated content
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


def _load_persona(role: str) -> str:
    """Read the markdown persona file for the given role."""
    path = _PERSONAS_DIR / f"{role}.md"
    return path.read_text(encoding="utf-8")


def _detect_ai_slop(text: str) -> bool:
    """Return True if 3 or more AI slop phrases are found in the text."""
    lower = text.lower()
    hits = sum(1 for phrase in _AI_SLOP_PHRASES if phrase.lower() in lower)
    return hits >= 3


async def _run_single_critique(
    role: str,
    resume_text: str,
    jd_text: str,
    trace_id: str | None,
) -> CritiqueResult:
    """Run one critique agent and return a validated CritiqueResult."""
    lf = Langfuse()
    span = lf.span(trace_id=trace_id, name=f"critique_{role}")

    persona_prompt = _load_persona(role)
    client = instructor.from_anthropic(
        anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    )

    user_msg = f"""
JOB DESCRIPTION:
{jd_text}

RESUME TO EVALUATE:
{resume_text}

Evaluate this resume as described in your persona instructions.
Respond ONLY with the CritiqueResult schema JSON.
""".strip()

    try:
        result: CritiqueResult = await client.messages.create(
            model=_MODEL,
            max_tokens=1024,
            system=persona_prompt,
            messages=[{"role": "user", "content": user_msg}],
            response_model=CritiqueResult,
        )
    except Exception as exc:
        logger.error("Critique agent '%s' failed: %s", role, exc)
        # Return a safe default rather than crashing the whole graph
        result = CritiqueResult(
            role=role,  # type: ignore[arg-type]
            score=0,
            flags=[f"Critique agent error: {exc}"],
            suggestions=[],
            ai_slop_detected=False,
            jd_match_confidence=0,
        )

    # Override ai_slop_detected with our local deterministic check
    # (the LLM may miss some patterns; this is a belt-and-suspenders check)
    result = result.model_copy(
        update={"ai_slop_detected": result.ai_slop_detected or _detect_ai_slop(resume_text)}
    )

    span.update(metadata={"score": result.score, "ai_slop": result.ai_slop_detected})
    span.end()
    return result


async def parallel_critique_node(state: GraphState) -> GraphState:
    """Fan out to three critique agents in parallel using asyncio.gather."""

    if state.cache_hit and state.critique_results:
        # Already have cached critiques — skip
        return state

    if not state.resume_output:
        return state.model_copy(update={"error": "No resume output to critique"})

    # Flatten the resume to a readable text block for critiquing
    r = state.resume_output
    resume_text = "\n\n".join([
        f"HEADLINE: {r.headline}",
        f"SUMMARY: {r.summary.content}",
        "EXPERIENCE:\n" + "\n".join(f"• {exp.content}" for exp in r.experience),
        f"SKILLS: {r.skills.content}",
        f"EDUCATION: {r.education.content}",
        f"Format: {r.format_used} | ATS Score: {r.ats_score_estimate} | Words: {r.word_count}",
    ])

    jd = state.jd_compressed or state.jd_raw

    recruiter_task, hm_task, expert_task = await asyncio.gather(
        _run_single_critique("recruiter", resume_text, jd, state.langfuse_trace_id),
        _run_single_critique("hiring_manager", resume_text, jd, state.langfuse_trace_id),
        _run_single_critique("expert", resume_text, jd, state.langfuse_trace_id),
        return_exceptions=False,
    )

    return state.model_copy(
        update={"critique_results": [recruiter_task, hm_task, expert_task]}
    )
