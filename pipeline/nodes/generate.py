"""
generate_node — call Claude claude-sonnet-4-6 via Instructor to produce a LaTeXOutput.

Flow:
1. Build system + user prompts from compressed JD, latex_analysis metrics,
   and optional regen consensus blocking issues
2. Call Claude claude-sonnet-4-6 with Instructor (response_model=LaTeXOutput)
3. On failure, fall back to GPT-4o
4. Validate Pydantic model (Instructor retries automatically on schema violation)
5. Record Langfuse span with token counts, word_count, bullet_count, and ATS score
"""

from __future__ import annotations

import logging
import os

import anthropic
import instructor
import openai
from langfuse import Langfuse

from pipeline.schemas import GraphState, LaTeXOutput

logger = logging.getLogger(__name__)

_PRIMARY_MODEL = "claude-sonnet-4-6"
_FALLBACK_MODEL = "gpt-4o"

_SYSTEM_PROMPT = """\
You are an expert resume writer specialising in ATS optimisation.

Your task:
- Produce a complete, single-page LaTeX resume document tailored precisely to the job description.
- The output MUST be a valid LaTeX document: start with \\documentclass{...} and include
  \\begin{document} ... \\end{document}.
- Use the specified writing format (STAR, XYZ, or CAR) consistently across ALL \\item bullets.
- Every bullet MUST contain at least one quantified outcome (%, $, time, or count).
- Keep total word count ≤ 600 words — hard constraint for single-page PDF layout.
- Avoid all "AI slop" phrases: leveraged synergies, results-driven, dynamic team player,
  proactively, thought leader, passionate about, spearheaded, drove alignment.
- Use strong past-tense action verbs: Built, Reduced, Increased, Designed, Launched, Migrated.
- Be specific: name real technologies, frameworks, and tools mentioned in the JD.
- Incorporate the LaTeX analysis keyword gaps where natural — do not force-insert them.

Respond ONLY with the structured JSON matching the LaTeXOutput schema.
The full_latex field must contain the complete LaTeX document.
"""


async def generate_node(state: GraphState) -> dict:
    """Generate a tailored LaTeX resume. Skipped on cache hits."""

    if state.get("cache_hit"):
        return {}

    lf = Langfuse()
    span = lf.start_observation(
        name="generate_latex_resume",
        metadata={"is_regen": state.get("human_decision") == "regen"},
    )

    jd = state.get("jd_compressed") or state["jd_raw"]

    # Build analysis context block
    analysis = state.get("latex_analysis") or {}
    analysis_block = f"""\
LaTeX Analysis of input resume:
- Total bullets: {analysis.get("total_bullets", "?")}
- Avg words per bullet: {analysis.get("avg_bullet_words", "?"):.1f}
- Sections detected: {", ".join(analysis.get("sections", []))}
- Keyword gaps (JD terms missing from resume): {", ".join(analysis.get("keyword_gaps", []) or ["none"])}
""" if analysis else ""

    # On regen, prepend consensus blocking issues to force the LLM to address them
    regen_block = ""
    if state.get("human_decision") == "regen" and state.get("consensus"):
        consensus = state["consensus"]
        blocking = consensus.blocking_issues if hasattr(consensus, "blocking_issues") else (consensus.get("blocking_issues") or [])
        if blocking:
            regen_block = "REQUIRED FIXES FROM PREVIOUS REVIEW (these MUST be addressed):\n"
            regen_block += "\n".join(f"- {issue}" for issue in blocking)
            regen_block += "\n\n"

    user_prompt = f"""\
{regen_block}JOB DESCRIPTION (compressed):
{jd}

{analysis_block}
Produce the tailored LaTeX resume strictly within the LaTeXOutput schema constraints.
The format_used field must match the writing format you actually used throughout.
""".strip()

    result: LaTeXOutput | None = None
    error_msg: str | None = None

    # ── Primary: Claude claude-sonnet-4-6 via Instructor ─────────────────────────────
    try:
        client = instructor.from_anthropic(
            anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        )
        result = await client.messages.create(
            model=_PRIMARY_MODEL,
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            response_model=LaTeXOutput,
        )
        span.update(metadata={
            "model": _PRIMARY_MODEL,
            "ats_score": result.ats_score_estimate,
            "word_count": result.word_count,
            "bullet_count": result.full_latex.count("\\item"),
        })
    except Exception as exc:
        error_msg = str(exc)
        logger.warning("Claude generation failed (%s) — falling back to GPT-4o", exc)
        span.update(metadata={"primary_error": error_msg})

    # ── Fallback: GPT-4o ──────────────────────────────────────────────────────
    if result is None:
        try:
            fallback_client = instructor.from_openai(
                openai.AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
            )
            result = await fallback_client.chat.completions.create(
                model=_FALLBACK_MODEL,
                max_tokens=4096,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_model=LaTeXOutput,
            )
            span.update(metadata={
                "model": _FALLBACK_MODEL,
                "ats_score": result.ats_score_estimate,
                "word_count": result.word_count,
                "bullet_count": result.full_latex.count("\\item"),
            })
        except Exception as exc:
            error_msg = f"Primary: {error_msg}; Fallback: {exc}"
            logger.error("Both LLM calls failed: %s", error_msg)

    span.end()

    if result is None:
        return {"error": f"Generation failed: {error_msg}"}

    return {"latex_output": result}
