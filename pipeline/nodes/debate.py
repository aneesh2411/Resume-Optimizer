"""
debate_node — personas respond to each other's flags, then a consensus is synthesised.

Flow:
1. Each persona reads the other personas' top flags and produces a DebateRound response
   (asyncio.gather for parallel execution).
2. All critiques + debate rounds are fed to Claude to produce a DebateConsensus.
3. critique_results is reset to [] so the operator.add accumulator is clean for regen paths.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import anthropic
import instructor
from langfuse import Langfuse

from pipeline.schemas import (
    CritiqueResult,
    DebateConsensus,
    DebateRound,
    GraphState,
)

logger = logging.getLogger(__name__)

_PERSONAS_DIR = Path(__file__).parent.parent / "personas"
_MODEL = "claude-haiku-4-5-20251001"


async def _run_debate_response(
    persona_id: str,
    own_critique: CritiqueResult,
    other_critiques: list[CritiqueResult],
    latex: str,
    jd: str,
    langfuse_trace_id: str | None,
) -> DebateRound:
    """Load persona prompt and respond to the other personas' flags."""
    persona_path = _PERSONAS_DIR / f"{persona_id}.md"
    if not persona_path.exists():
        raise FileNotFoundError(f"Persona markdown not found: {persona_path}")

    persona_prompt = persona_path.read_text(encoding="utf-8")

    lf = Langfuse()
    span = lf.start_observation(
        name=f"debate_{persona_id}",
        metadata={"persona_id": persona_id},
    )

    other_flags_text = "\n".join(
        f"- [{c.persona_id}] {flag}"
        for c in other_critiques
        for flag in c.flags[:3]
    ) or "(no other reviewers)"

    other_ids = [c.persona_id for c in other_critiques]

    user_msg = f"""\
JOB DESCRIPTION:
{jd}

LATEX RESUME:
{latex[:3000]}

YOUR PREVIOUS CRITIQUE:
Score: {own_critique.score}
Flags: {'; '.join(own_critique.flags)}

OTHER REVIEWERS' TOP FLAGS:
{other_flags_text}

Review the other reviewers' flags. State what you agree with, what you disagree with,
and synthesise your updated position in one paragraph.
Respond ONLY with the DebateRound schema JSON.
Use responding_persona_id="{persona_id}".
Use responding_to_persona_ids={other_ids!r}.
""".strip()

    client = instructor.from_anthropic(
        anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    )

    try:
        round_result: DebateRound = await client.messages.create(
            model=_MODEL,
            max_tokens=512,
            system=persona_prompt,
            messages=[{"role": "user", "content": user_msg}],
            response_model=DebateRound,
        )
        # Force responding_persona_id to match
        round_result = round_result.model_copy(
            update={"responding_persona_id": persona_id}
        )
    except Exception as exc:
        logger.error("Debate response for '%s' failed: %s", persona_id, exc)
        round_result = DebateRound(
            responding_persona_id=persona_id,
            responding_to_persona_ids=other_ids,
            agreements=[],
            disagreements=[],
            synthesis=f"(error: {str(exc)[:200]})",
        )

    span.update(metadata={"responding_persona_id": round_result.responding_persona_id})
    span.end()

    return round_result


async def _synthesise_consensus(
    critiques: list[CritiqueResult],
    rounds: list[DebateRound],
    langfuse_trace_id: str | None,
) -> DebateConsensus:
    """Feed all critiques + debate rounds to Claude and extract a DebateConsensus."""
    lf = Langfuse()
    span = lf.start_observation(
        name="debate_consensus",
        metadata={"persona_count": len(critiques)},
    )

    critiques_text = "\n".join(
        f"[{c.persona_id}] score={c.score} flags={c.flags} suggestions={c.suggestions}"
        for c in critiques
    )
    rounds_text = "\n".join(
        f"[{r.responding_persona_id}] agreements={r.agreements} "
        f"disagreements={r.disagreements} synthesis={r.synthesis}"
        for r in rounds
    )

    system_prompt = (
        "You are an expert technical writing coordinator. "
        "Synthesise the critique panel's findings into a single consensus verdict."
    )

    user_msg = f"""\
INITIAL CRITIQUES:
{critiques_text}

DEBATE RESPONSES:
{rounds_text}

Based on the above, produce a DebateConsensus JSON that captures:
- blocking_issues: issues raised by 2+ reviewers (must fix before approval)
- optional_improvements: suggestions raised by only 1 reviewer
- consensus_score: weighted average of all scores (0-100)
- summary: 1-2 sentence verdict
""".strip()

    client = instructor.from_anthropic(
        anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    )

    try:
        consensus: DebateConsensus = await client.messages.create(
            model=_MODEL,
            max_tokens=512,
            system=system_prompt,
            messages=[{"role": "user", "content": user_msg}],
            response_model=DebateConsensus,
        )
    except Exception as exc:
        logger.error("Consensus synthesis failed: %s", exc)
        all_flags = list({f for c in critiques for f in c.flags})
        consensus = DebateConsensus(
            blocking_issues=all_flags[:5],
            optional_improvements=[],
            consensus_score=int(sum(c.score for c in critiques) / max(len(critiques), 1)),
            summary=f"Consensus synthesis failed: {str(exc)[:200]}",
        )

    span.update(metadata={
        "consensus_score": consensus.consensus_score,
        "blocking_count": len(consensus.blocking_issues),
    })
    span.end()

    return consensus


async def debate_node(state: GraphState) -> dict:
    """
    Run one debate round per persona (parallel), then synthesise a DebateConsensus.

    Returns {"consensus": DebateConsensus, "critique_results": []} — the empty list
    resets the operator.add accumulator so regen paths start fresh.
    """
    critiques: list[CritiqueResult] = state.get("critique_results", [])
    latex_output = state.get("latex_output")
    latex = getattr(latex_output, "full_latex", "") if latex_output else ""
    jd = state.get("jd_compressed") or state["jd_raw"]
    trace_id = state.get("langfuse_trace_id")

    # Run all debate responses in parallel
    tasks = [
        _run_debate_response(
            persona_id=c.persona_id,
            own_critique=c,
            other_critiques=[x for x in critiques if x.persona_id != c.persona_id],
            latex=latex,
            jd=jd,
            langfuse_trace_id=trace_id,
        )
        for c in critiques
    ]
    rounds: list[DebateRound] = await asyncio.gather(*tasks)

    consensus = await _synthesise_consensus(critiques, list(rounds), trace_id)

    # Reset critique_results so the accumulator is clean for any regen path
    return {"consensus": consensus, "critique_results": []}
