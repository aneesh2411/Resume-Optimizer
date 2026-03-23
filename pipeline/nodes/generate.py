"""
generate_node — call Claude claude-sonnet-4-6 via Instructor to produce a structured ResumeOutput.

Flow:
1. Build system + user prompts from compressed JD, optional resume context, and iteration feedback
2. Call Claude claude-sonnet-4-6 with Instructor (response_model=ResumeOutput)
3. On failure, fall back to GPT-4o
4. Validate Pydantic model (Instructor retries automatically on schema violation)
5. Record Langfuse span with token counts and ATS score
"""

from __future__ import annotations

import logging
import os
from typing import Any

import anthropic
import instructor
import openai
from langfuse import Langfuse

from pipeline.schemas import GraphState, ResumeOutput

logger = logging.getLogger(__name__)

_PRIMARY_MODEL = "claude-sonnet-4-6"
_FALLBACK_MODEL = "gpt-4o"

_SYSTEM_PROMPT = """\
You are an expert resume writer specialising in ATS optimisation and targeted resume tailoring.

Your task:
- Produce a single-page resume tailored precisely to the job description.
- Use the specified writing format (STAR, XYZ, or CAR) consistently across ALL experience bullets.
- Every bullet in the experience section MUST contain at least one quantified outcome (%, $, time, count).
- Keep total word count ≤ 600 words — this is a hard constraint for single-page layout.
- Avoid all "AI slop" phrases: leveraged synergies, results-driven, dynamic team player, proactively,
  thought leader, passionate about, spearheaded, drove alignment, cross-functional collaboration.
- Use strong past-tense action verbs: Built, Reduced, Increased, Designed, Launched, Migrated, etc.
- Be specific: name real technologies, frameworks, and tools from the JD.

Respond ONLY with the structured JSON matching the ResumeOutput schema.
"""


async def generate_node(state: GraphState) -> GraphState:
    """Generate a tailored resume. Skipped on cache hits."""

    if state.cache_hit:
        return state

    lf = Langfuse()
    span = lf.span(
        trace_id=state.langfuse_trace_id,
        name="generate_resume",
        metadata={"iteration": state.iteration_count},
    )

    jd = state.jd_compressed or state.jd_raw
    resume_context = state.resume_raw or "(no existing resume provided)"
    feedback = state.user_iteration_feedback or "(first generation — no feedback yet)"

    user_prompt = f"""\
JOB DESCRIPTION (compressed):
{jd}

CANDIDATE'S EXISTING RESUME:
{resume_context}

ITERATION FEEDBACK FROM CANDIDATE:
{feedback}

Produce the tailored resume strictly within the ResumeOutput schema constraints.
The format_used field must match the writing format you actually used throughout.
""".strip()

    resume: ResumeOutput | None = None
    error_msg: str | None = None

    # ── Primary: Claude claude-sonnet-4-6 via Instructor ─────────────────────────────
    try:
        client = instructor.from_anthropic(anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"]))
        resume = await client.messages.create(
            model=_PRIMARY_MODEL,
            max_tokens=2048,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            response_model=ResumeOutput,
        )
        span.update(metadata={"model": _PRIMARY_MODEL, "ats_score": resume.ats_score_estimate, "word_count": resume.word_count})
    except Exception as exc:
        error_msg = str(exc)
        logger.warning("Claude generation failed (%s) — falling back to GPT-4o", exc)
        span.update(metadata={"primary_error": error_msg})

    # ── Fallback: GPT-4o ──────────────────────────────────────────────────────
    if resume is None:
        try:
            fallback_client = instructor.from_openai(
                openai.AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
            )
            resume = await fallback_client.chat.completions.create(
                model=_FALLBACK_MODEL,
                max_tokens=2048,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_model=ResumeOutput,
            )
            span.update(metadata={"model": _FALLBACK_MODEL, "ats_score": resume.ats_score_estimate, "word_count": resume.word_count})
        except Exception as exc:
            error_msg = f"Primary: {error_msg}; Fallback: {exc}"
            logger.error("Both LLM calls failed: %s", error_msg)

    span.end()

    if resume is None:
        return state.model_copy(update={"error": f"Generation failed: {error_msg}"})

    return state.model_copy(
        update={
            "resume_output": resume,
            "iteration_count": state.iteration_count + 1,
        }
    )
