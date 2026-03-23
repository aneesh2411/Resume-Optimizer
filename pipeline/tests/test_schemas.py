"""
Tests for Pydantic schema validation.

These tests verify the hard constraints defined in schemas.py:
- word_count hard cap of 600
- skills/education max 150 chars
- experience max 3 roles
- headline max 80 chars
"""

import pytest
from pydantic import ValidationError

from pipeline.schemas import (
    ConflictResolution,
    CritiqueResult,
    GraphState,
    ResumeOutput,
    ResumeSection,
)


# ── ResumeSection ─────────────────────────────────────────────────────────────

def test_resume_section_accepts_normal_content():
    s = ResumeSection(content="Built a high-performance API")
    assert s.content == "Built a high-performance API"


def test_resume_section_rejects_content_over_300_chars():
    with pytest.raises(ValidationError):
        ResumeSection(content="x" * 301)


def test_resume_section_accepts_exactly_300_chars():
    ResumeSection(content="x" * 300)


# ── ResumeOutput ──────────────────────────────────────────────────────────────

def _valid_resume(**overrides) -> dict:
    base = {
        "headline": "Senior Software Engineer at Acme Corp",
        "summary": {"content": "10 years building distributed systems. Led teams of 8."},
        "experience": [
            {"content": "Built Python microservices handling 50k req/s. Reduced latency 40%."},
            {"content": "Led migration from monolith to k8s. Cut infra cost by $200k/yr."},
        ],
        "skills": {"content": "Python, Go, Kubernetes, PostgreSQL, Redis"},
        "education": {"content": "BSc Computer Science, MIT, 2014"},
        "format_used": "XYZ",
        "ats_score_estimate": 85,
        "word_count": 60,
    }
    base.update(overrides)
    return base


def test_resume_output_valid():
    r = ResumeOutput(**_valid_resume())
    assert r.ats_score_estimate == 85


def test_resume_output_rejects_word_count_over_600():
    with pytest.raises(ValidationError):
        ResumeOutput(**_valid_resume(word_count=601))


def test_resume_output_accepts_word_count_600():
    r = ResumeOutput(**_valid_resume(word_count=600))
    assert r.word_count == 600


def test_resume_output_rejects_headline_over_80_chars():
    with pytest.raises(ValidationError):
        ResumeOutput(**_valid_resume(headline="x" * 81))


def test_resume_output_rejects_skills_over_150_chars():
    with pytest.raises(ValidationError):
        ResumeOutput(**_valid_resume(skills={"content": "x" * 151}))


def test_resume_output_rejects_education_over_150_chars():
    with pytest.raises(ValidationError):
        ResumeOutput(**_valid_resume(education={"content": "x" * 151}))


def test_resume_output_rejects_over_3_experience_roles():
    with pytest.raises(ValidationError):
        ResumeOutput(
            **_valid_resume(
                experience=[
                    {"content": "Role 1 — built X, achieved Y."},
                    {"content": "Role 2 — built X, achieved Y."},
                    {"content": "Role 3 — built X, achieved Y."},
                    {"content": "Role 4 — built X, achieved Y."},  # exceeds max_length=3
                ]
            )
        )


def test_resume_output_rejects_zero_experience_roles():
    with pytest.raises(ValidationError):
        ResumeOutput(**_valid_resume(experience=[]))


def test_resume_output_rejects_invalid_format():
    with pytest.raises(ValidationError):
        ResumeOutput(**_valid_resume(format_used="INVALID"))


def test_resume_output_rejects_ats_score_over_100():
    with pytest.raises(ValidationError):
        ResumeOutput(**_valid_resume(ats_score_estimate=101))


# ── CritiqueResult ────────────────────────────────────────────────────────────

def test_critique_result_valid():
    c = CritiqueResult(
        role="recruiter",
        score=75,
        flags=["Missing keyword: Python"],
        suggestions=["Add Python to skills section"],
        ai_slop_detected=False,
        jd_match_confidence=80,
    )
    assert c.role == "recruiter"


def test_critique_result_rejects_invalid_role():
    with pytest.raises(ValidationError):
        CritiqueResult(
            role="ceo",  # not a valid role
            score=75,
            flags=[],
            suggestions=[],
            ai_slop_detected=False,
            jd_match_confidence=80,
        )


def test_critique_result_rejects_score_over_100():
    with pytest.raises(ValidationError):
        CritiqueResult(
            role="recruiter",
            score=101,
            flags=[],
            suggestions=[],
            ai_slop_detected=False,
            jd_match_confidence=50,
        )


# ── GraphState ────────────────────────────────────────────────────────────────

def test_graph_state_defaults():
    s = GraphState(jd_raw="Software engineer role at Acme Corp")
    assert s.cache_hit is False
    assert s.iteration_count == 0
    assert s.critique_results == []
    assert s.approved is False


def test_graph_state_model_copy_update():
    s = GraphState(jd_raw="test jd")
    updated = s.model_copy(update={"jd_compressed": "short jd", "cache_hit": True})
    assert updated.jd_compressed == "short jd"
    assert updated.cache_hit is True
    # Original unchanged
    assert s.jd_compressed is None
    assert s.cache_hit is False
