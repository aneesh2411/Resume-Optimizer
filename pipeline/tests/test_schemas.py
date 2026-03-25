"""
Tests for pipeline/schemas.py.

Covers:
- LaTeXOutput Pydantic constraints
- CritiqueResult accepts arbitrary persona_id strings
- GraphState can be dict-constructed
- DebateConsensus validation
"""

import pytest
from pydantic import ValidationError

from pipeline.schemas import (
    CritiqueResult,
    DebateConsensus,
    DebateRound,
    GraphState,
    LaTeXAnalysis,
    LaTeXOutput,
    LaTeXSection,
)


# ── LaTeXSection ──────────────────────────────────────────────────────────────

def test_latex_section_accepts_normal_content():
    s = LaTeXSection(name="Experience", content="Built distributed systems.")
    assert s.name == "Experience"


def test_latex_section_rejects_content_over_2000_chars():
    with pytest.raises(ValidationError):
        LaTeXSection(name="X", content="x" * 2001)


# ── LaTeXOutput ───────────────────────────────────────────────────────────────

_VALID_LATEX = r"""\documentclass{article}
\begin{document}
\section{Experience}
\begin{itemize}
\item Built Python microservices handling 50k req/s, reducing latency by 40\%.
\end{itemize}
\end{document}"""


def _valid_latex_output(**overrides) -> dict:
    base = {
        "full_latex": _VALID_LATEX,
        "sections": [],
        "format_used": "XYZ",
        "ats_score_estimate": 85,
        "word_count": 50,
    }
    base.update(overrides)
    return base


def test_latex_output_valid():
    o = LaTeXOutput(**_valid_latex_output())
    assert o.ats_score_estimate == 85
    assert o.format_used == "XYZ"


def test_latex_output_requires_begin_document():
    with pytest.raises((ValidationError, ValueError)):
        LaTeXOutput(**_valid_latex_output(full_latex=r"\documentclass{article}\n% no begin document"))


def test_latex_output_rejects_word_count_over_600():
    with pytest.raises(ValidationError):
        LaTeXOutput(**_valid_latex_output(word_count=601))


def test_latex_output_accepts_word_count_600():
    o = LaTeXOutput(**_valid_latex_output(word_count=600))
    assert o.word_count == 600


def test_latex_output_rejects_ats_score_over_100():
    with pytest.raises(ValidationError):
        LaTeXOutput(**_valid_latex_output(ats_score_estimate=101))


def test_latex_output_rejects_invalid_format():
    with pytest.raises(ValidationError):
        LaTeXOutput(**_valid_latex_output(format_used="INVALID"))


def test_latex_output_accepts_all_valid_formats():
    for fmt in ("STAR", "XYZ", "CAR"):
        o = LaTeXOutput(**_valid_latex_output(format_used=fmt))
        assert o.format_used == fmt


# ── CritiqueResult ────────────────────────────────────────────────────────────

def test_critique_result_accepts_arbitrary_persona_id():
    c = CritiqueResult(
        persona_id="faang_bar_raiser",
        score=72,
        flags=["No quantified impact"],
        suggestions=["Add metrics"],
        ai_slop_detected=False,
        jd_match_confidence=80,
    )
    assert c.persona_id == "faang_bar_raiser"


def test_critique_result_accepts_any_string_persona_id():
    """persona_id is a free-form string, not a Literal."""
    c = CritiqueResult(
        persona_id="my_custom_persona_xyz",
        score=50,
        flags=[],
        suggestions=[],
        ai_slop_detected=True,
        jd_match_confidence=60,
    )
    assert c.persona_id == "my_custom_persona_xyz"


def test_critique_result_rejects_score_over_100():
    with pytest.raises(ValidationError):
        CritiqueResult(
            persona_id="ats_recruiter",
            score=101,
            flags=[],
            suggestions=[],
            ai_slop_detected=False,
            jd_match_confidence=50,
        )


def test_critique_result_rejects_jd_match_confidence_over_100():
    with pytest.raises(ValidationError):
        CritiqueResult(
            persona_id="startup_cto",
            score=80,
            flags=[],
            suggestions=[],
            ai_slop_detected=False,
            jd_match_confidence=101,
        )


# ── DebateRound ───────────────────────────────────────────────────────────────

def test_debate_round_valid():
    r = DebateRound(
        responding_persona_id="startup_cto",
        responding_to_persona_ids=["faang_bar_raiser", "ats_recruiter"],
        agreements=["Missing metrics is valid flag"],
        disagreements=[],
        synthesis="Agree on impact quantification being the priority fix.",
    )
    assert r.responding_persona_id == "startup_cto"
    assert len(r.responding_to_persona_ids) == 2


# ── DebateConsensus ───────────────────────────────────────────────────────────

def test_debate_consensus_valid():
    c = DebateConsensus(
        blocking_issues=["No quantified impact in any role"],
        optional_improvements=["Add GitHub profile link"],
        consensus_score=65,
        summary="Critical: metrics missing. Keyword gaps manageable.",
    )
    assert c.consensus_score == 65
    assert len(c.blocking_issues) == 1


def test_debate_consensus_rejects_score_over_100():
    with pytest.raises(ValidationError):
        DebateConsensus(
            blocking_issues=[],
            optional_improvements=[],
            consensus_score=101,
            summary="test",
        )


def test_debate_consensus_defaults_empty_lists():
    c = DebateConsensus(consensus_score=75, summary="OK")
    assert c.blocking_issues == []
    assert c.optional_improvements == []


# ── GraphState ────────────────────────────────────────────────────────────────

def test_graph_state_can_be_dict_constructed():
    s: GraphState = {
        "jd_raw": "Software engineer role at Acme Corp",
        "latex_input": r"\begin{document}hello\end{document}",
        "selected_persona_ids": ["faang_bar_raiser"],
        "cache_hit": False,
        "compression_attempts": 0,
        "overflow_error": False,
        "critique_results": [],
    }
    assert s["jd_raw"] == "Software engineer role at Acme Corp"
    assert s["cache_hit"] is False
    assert s["critique_results"] == []


def test_graph_state_critique_results_is_list():
    s: GraphState = {
        "jd_raw": "test jd",
        "latex_input": r"\begin{document}\end{document}",
        "selected_persona_ids": ["startup_cto"],
        "cache_hit": False,
        "compression_attempts": 0,
        "overflow_error": False,
        "critique_results": [],
    }
    c = CritiqueResult(
        persona_id="startup_cto",
        score=80,
        flags=[],
        suggestions=[],
        ai_slop_detected=False,
        jd_match_confidence=75,
    )
    s["critique_results"] = s["critique_results"] + [c]
    assert len(s["critique_results"]) == 1
    assert s["critique_results"][0].persona_id == "startup_cto"


def test_graph_state_optional_fields_default_absent():
    """TypedDict fields marked Optional need not be present."""
    s: GraphState = {
        "jd_raw": "test",
        "latex_input": r"\begin{document}\end{document}",
        "selected_persona_ids": [],
        "cache_hit": False,
        "compression_attempts": 0,
        "overflow_error": False,
        "critique_results": [],
    }
    assert s.get("error") is None
    assert s.get("pdf_url") is None
    assert s.get("latex_output") is None
