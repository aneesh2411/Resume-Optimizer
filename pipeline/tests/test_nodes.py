"""
Tests for pipeline nodes (without LLM calls — pure unit tests).
"""

import pytest

from pipeline.nodes.ingest import ingest_node
from pipeline.nodes.iterate import iterate_node
from pipeline.schemas import GraphState, ResumeOutput, ResumeSection, CritiqueResult, ConflictResolution


# ── ingest_node ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ingest_node_passes_valid_jd():
    state = GraphState(jd_raw="We are looking for a software engineer with 5+ years Python experience.")
    result = await ingest_node(state)
    assert result.error is None
    assert result.jd_raw.startswith("We are looking")


@pytest.mark.asyncio
async def test_ingest_node_rejects_short_jd():
    state = GraphState(jd_raw="Too short")
    result = await ingest_node(state)
    assert result.error is not None
    assert "too short" in result.error.lower()


@pytest.mark.asyncio
async def test_ingest_node_truncates_long_jd():
    long_jd = "x " * 5000  # ~10 000 chars
    state = GraphState(jd_raw=long_jd)
    result = await ingest_node(state)
    assert result.error is None
    assert len(result.jd_raw) <= 8000


@pytest.mark.asyncio
async def test_ingest_node_strips_null_bytes():
    state = GraphState(jd_raw="Software\x00 engineer role with Python experience required.")
    result = await ingest_node(state)
    assert "\x00" not in result.jd_raw


# ── iterate_node ──────────────────────────────────────────────────────────────

def _make_resume() -> ResumeOutput:
    return ResumeOutput(
        headline="Software Engineer",
        summary=ResumeSection(content="5 years Python."),
        experience=[ResumeSection(content="Built APIs handling 10k req/s, reducing latency by 30%.")],
        skills=ResumeSection(content="Python, FastAPI, PostgreSQL"),
        education=ResumeSection(content="BSc CS, MIT 2018"),
        format_used="XYZ",
        ats_score_estimate=80,
        word_count=25,
    )


@pytest.mark.asyncio
async def test_iterate_node_clears_outputs():
    critique = CritiqueResult(
        role="recruiter",
        score=70,
        flags=["Missing keyword"],
        suggestions=["Add Python"],
        ai_slop_detected=False,
        jd_match_confidence=75,
    )
    state = GraphState(
        jd_raw="Python engineer role",
        resume_output=_make_resume(),
        critique_results=[critique],
        cache_hit=True,
    )
    result = await iterate_node(state)

    assert result.resume_output is None
    assert result.critique_results == []
    assert result.conflict_resolution is None
    assert result.cache_hit is False  # force fresh LLM call


@pytest.mark.asyncio
async def test_iterate_node_preserves_jd_and_feedback():
    state = GraphState(
        jd_raw="Python engineer role",
        user_iteration_feedback="Make the summary shorter",
        resume_output=_make_resume(),
    )
    result = await iterate_node(state)
    assert result.jd_raw == "Python engineer role"
    assert result.user_iteration_feedback == "Make the summary shorter"
