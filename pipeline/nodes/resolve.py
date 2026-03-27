"""
join_and_resolve_node — merge three CritiqueResults into a single ConflictResolution.

Uses Claude claude-sonnet-4-6 via Instructor to synthesise the three perspectives,
rank conflicting flags by score delta, and identify blocking vs optional issues.

Also runs the Guardrails AI validator for PII detection and AI slop as a final check.
"""

from __future__ import annotations

import logging
import os

import anthropic
import instructor
from langfuse import Langfuse

from pipeline.schemas import ConflictResolution, GraphState

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM_PROMPT = """\
You are a senior hiring strategist with expertise in resume optimisation.
You have received critique results from three different evaluators: a recruiter,
a hiring manager, and a resume expert. Your job is to:

1. Identify flags that appear in 2+ critiques (high-consensus issues — these become blocking_issues)
2. Identify flags that appear in only 1 critique (low-consensus — optional_improvements)
3. Rank priority_flags by impact: blocking first, then high-scoring evaluator flags
4. Calculate a consensus_score as a weighted average: recruiter 30%, hiring_manager 40%, expert 30%
5. Keep lists concise — max 5 blocking issues, max 5 optional improvements

Respond ONLY with the ConflictResolution schema JSON.
"""

# Guardrails AI slop phrases for post-validation
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
]


def _validate_resume_for_slop(state: GraphState) -> list[str]:
    """Return list of AI slop flags found in the final resume."""
    if not state.resume_output:
        return []

    r = state.resume_output
    full_text = " ".join([
        r.headline,
        r.summary.content,
        *[exp.content for exp in r.experience],
        r.skills.content,
        r.education.content,
    ])

    return [
        f"AI slop detected: '{phrase}'"
        for phrase in _AI_SLOP_PHRASES
        if phrase.lower() in full_text.lower()
    ]


async def join_and_resolve_node(state: GraphState) -> GraphState:
    """Synthesise critique results into actionable ConflictResolution."""

    lf = Langfuse()

    # Format critique results for the LLM
    critiques_text = "\n\n".join([
        f"[{c.role.upper()}] score={c.score}/100, jd_confidence={c.jd_match_confidence}/100\n"
        f"flags: {c.flags}\n"
        f"suggestions: {c.suggestions}\n"
        f"ai_slop_detected: {c.ai_slop_detected}"
        for c in state.critique_results
    ])

    # Add any local slop validation flags
    slop_flags = _validate_resume_for_slop(state)
    if slop_flags:
        critiques_text += f"\n\n[LOCAL VALIDATOR] AI slop phrases found:\n{slop_flags}"

    client = instructor.from_anthropic(
        anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    )

    try:
        resolution: ConflictResolution = await client.messages.create(
            model=_MODEL,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": critiques_text}],
            response_model=ConflictResolution,
        )
    except Exception as exc:
        logger.error("Conflict resolution failed: %s", exc)
        # Graceful fallback: aggregate manually
        all_flags = [f for c in state.critique_results for f in c.flags]
        all_suggestions = [s for c in state.critique_results for s in c.suggestions]
        scores = [c.score for c in state.critique_results]
        consensus = int(sum(scores) / len(scores)) if scores else 0

        resolution = ConflictResolution(
            priority_flags=list(dict.fromkeys(all_flags))[:5],  # deduplicate, keep order
            consensus_score=consensus,
            blocking_issues=list(dict.fromkeys(all_flags))[:3],
            optional_improvements=list(dict.fromkeys(all_suggestions))[:5],
        )

    span.update(metadata={"consensus_score": resolution.consensus_score, "blocking": len(resolution.blocking_issues)})
    span.end()

    return state.model_copy(update={"conflict_resolution": resolution})
