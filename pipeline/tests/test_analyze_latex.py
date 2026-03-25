"""
Tests for analyze_latex_node — pure regex, no LLM, no mocks needed.
"""

from __future__ import annotations

import pytest

from pipeline.nodes.analyze_latex import analyze_latex, analyze_latex_node
from pipeline.schemas import GraphState


_SAMPLE_LATEX = r"""
\documentclass{article}
\begin{document}

\section{Experience}
\begin{itemize}
\item Built Python microservices handling 50k req/s, reducing latency by 40\%.
\item Led migration from monolith to Kubernetes, cutting infra cost by \$200k/yr.
\item Designed PostgreSQL schema for multi-tenant SaaS product.
\end{itemize}

\subsection{Earlier roles}
\begin{itemize}
\item Maintained legacy Java codebase and added unit tests.
\end{itemize}

\section{Skills}
Python, Go, Kubernetes, PostgreSQL

\end{document}
"""

_SAMPLE_JD = (
    "We need a Python expert with Kubernetes, Terraform, and AWS experience. "
    "Experience with Go and PostgreSQL is a plus. Familiarity with Terraform strongly preferred."
)


# ── analyze_latex() ───────────────────────────────────────────────────────────

def test_bullet_count():
    result = analyze_latex(_SAMPLE_LATEX, _SAMPLE_JD)
    assert result["total_bullets"] == 4


def test_avg_bullet_words_is_positive():
    result = analyze_latex(_SAMPLE_LATEX, _SAMPLE_JD)
    assert result["avg_bullet_words"] > 0


def test_section_extraction():
    result = analyze_latex(_SAMPLE_LATEX, _SAMPLE_JD)
    assert "Experience" in result["sections"]
    assert "Skills" in result["sections"]


def test_subsection_extraction():
    result = analyze_latex(_SAMPLE_LATEX, _SAMPLE_JD)
    assert "Earlier roles" in result["sections"]


def test_section_count():
    result = analyze_latex(_SAMPLE_LATEX, _SAMPLE_JD)
    assert result["section_count"] == 3  # Experience, Earlier roles, Skills


def test_keyword_gaps_detect_missing_terms():
    """Terraform and AWS appear in JD but not in the LaTeX."""
    result = analyze_latex(_SAMPLE_LATEX, _SAMPLE_JD)
    assert "Terraform" in result["keyword_gaps"]
    assert "AWS" in result["keyword_gaps"]


def test_keyword_gaps_exclude_present_terms():
    """Python, Kubernetes, PostgreSQL are in the LaTeX — should NOT be in gaps."""
    result = analyze_latex(_SAMPLE_LATEX, _SAMPLE_JD)
    assert "Python" not in result["keyword_gaps"]
    assert "Kubernetes" not in result["keyword_gaps"]
    assert "PostgreSQL" not in result["keyword_gaps"]


def test_keyword_gaps_capped_at_10():
    """Even with many gaps, the list is truncated to 10."""
    jd_many_keywords = " ".join(f"Technology{i}" for i in range(50))
    result = analyze_latex(r"\begin{document}\end{document}", jd_many_keywords)
    assert len(result["keyword_gaps"]) <= 10


def test_empty_latex_returns_zeros():
    result = analyze_latex(r"\begin{document}\end{document}", _SAMPLE_JD)
    assert result["total_bullets"] == 0
    assert result["section_count"] == 0
    assert result["avg_bullet_words"] == 0.0


def test_total_words_strips_commands():
    """LaTeX commands should be stripped before word count."""
    latex = r"\begin{document}\section{Skills}Python Go Rust\end{document}"
    result = analyze_latex(latex, "")
    # Should count "Python", "Go", "Rust" (LaTeX commands stripped)
    assert result["total_words"] >= 3


# ── analyze_latex_node() ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_analyze_latex_node_returns_latex_analysis():
    state: GraphState = {
        "jd_raw": _SAMPLE_JD,
        "latex_input": _SAMPLE_LATEX,
        "selected_persona_ids": ["faang_bar_raiser"],
        "cache_hit": False,
        "compression_attempts": 0,
        "overflow_error": False,
        "critique_results": [],
    }
    result = await analyze_latex_node(state)
    assert "latex_analysis" in result
    analysis = result["latex_analysis"]
    assert analysis["total_bullets"] == 4
    assert "Experience" in analysis["sections"]


@pytest.mark.asyncio
async def test_analyze_latex_node_uses_jd_compressed_when_available():
    """When jd_compressed is present it should be used for gap analysis."""
    state: GraphState = {
        "jd_raw": "irrelevant raw jd",
        "jd_compressed": "We need Terraform and AWS skills.",
        "latex_input": _SAMPLE_LATEX,
        "selected_persona_ids": ["faang_bar_raiser"],
        "cache_hit": False,
        "compression_attempts": 0,
        "overflow_error": False,
        "critique_results": [],
    }
    result = await analyze_latex_node(state)
    analysis = result["latex_analysis"]
    # Terraform and AWS are in the compressed JD but not in the LaTeX
    assert "Terraform" in analysis["keyword_gaps"] or "AWS" in analysis["keyword_gaps"]
