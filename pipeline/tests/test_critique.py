"""
Tests for critique.py — fan_out_to_personas and critique_persona_node.

LLM calls are mocked; file system access is real (uses existing persona .md files).
"""

from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langgraph.types import Send

from pipeline.nodes.critique import fan_out_to_personas, critique_persona_node, _detect_ai_slop
from pipeline.schemas import CritiqueResult, GraphState, LaTeXOutput


# ── Fixtures ──────────────────────────────────────────────────────────────────

_SAMPLE_LATEX = r"""
\documentclass{article}
\begin{document}
\section{Experience}
\begin{itemize}
\item Built Python microservices handling 50k req/s.
\end{itemize}
\end{document}
"""

_LATEX_OUTPUT = LaTeXOutput(
    full_latex=_SAMPLE_LATEX,
    format_used="STAR",
    word_count=80,
    ats_score_estimate=75,
)

_SAMPLE_CRITIQUE = CritiqueResult(
    persona_id="recruiter",
    score=72,
    flags=["Missing quantified impact"],
    suggestions=["Add metrics to each bullet"],
    ai_slop_detected=False,
    jd_match_confidence=65,
)


def _make_state(**overrides) -> GraphState:
    base: GraphState = {
        "jd_raw": "We need Python and Kubernetes skills.",
        "latex_input": _SAMPLE_LATEX,
        "selected_persona_ids": ["recruiter"],
        "cache_hit": False,
        "compression_attempts": 0,
        "overflow_error": False,
        "critique_results": [],
        "latex_output": _LATEX_OUTPUT,
    }
    base.update(overrides)
    return base


# ── _detect_ai_slop ───────────────────────────────────────────────────────────

def test_ai_slop_detects_3_or_more_phrases():
    sloppy = "I spearheaded cross-functional collaboration and championed thought leader initiatives."
    assert _detect_ai_slop(sloppy) is True


def test_ai_slop_below_threshold_returns_false():
    mild = "I spearheaded the project and leveraged synergies."
    assert _detect_ai_slop(mild) is False  # only 2 phrases


def test_ai_slop_case_insensitive():
    sloppy = "SPEARHEADED Cross-Functional Collaboration CHAMPIONED Thought Leader driven."
    assert _detect_ai_slop(sloppy) is True


# ── fan_out_to_personas ───────────────────────────────────────────────────────

def test_fan_out_returns_one_send_per_persona():
    state = _make_state(selected_persona_ids=["recruiter", "hiring_manager", "expert"])
    sends = fan_out_to_personas(state)
    assert len(sends) == 3


def test_fan_out_sends_are_send_objects():
    state = _make_state(selected_persona_ids=["recruiter"])
    sends = fan_out_to_personas(state)
    assert all(isinstance(s, Send) for s in sends)


def test_fan_out_targets_critique_persona_node():
    state = _make_state(selected_persona_ids=["recruiter", "hiring_manager"])
    sends = fan_out_to_personas(state)
    for send in sends:
        assert send.node == "critique_persona"


def test_fan_out_persona_ids_are_correct():
    persona_ids = ["recruiter", "hiring_manager", "expert"]
    state = _make_state(selected_persona_ids=persona_ids)
    sends = fan_out_to_personas(state)
    sent_ids = [s.arg["persona_id"] for s in sends]
    assert sorted(sent_ids) == sorted(persona_ids)


def test_fan_out_passes_latex_output():
    state = _make_state(selected_persona_ids=["recruiter"])
    sends = fan_out_to_personas(state)
    assert sends[0].arg["latex_output"] is _LATEX_OUTPUT


def test_fan_out_passes_jd_raw():
    state = _make_state(selected_persona_ids=["recruiter"])
    sends = fan_out_to_personas(state)
    assert sends[0].arg["jd_raw"] == state["jd_raw"]


def test_fan_out_empty_persona_ids_returns_empty():
    state = _make_state(selected_persona_ids=[])
    sends = fan_out_to_personas(state)
    assert sends == []


# ── critique_persona_node ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_critique_persona_node_returns_critique_results_list():
    persona_state = {
        "persona_id": "recruiter",
        "latex_output": _LATEX_OUTPUT,
        "jd_raw": "Python and Kubernetes experience required.",
        "jd_compressed": None,
        "latex_analysis": None,
        "langfuse_trace_id": None,
    }
    mock_result = _SAMPLE_CRITIQUE.model_copy()

    with patch("pipeline.nodes.critique.instructor") as mock_instructor, \
         patch("pipeline.nodes.critique.anthropic") as mock_anthropic, \
         patch("pipeline.nodes.critique.Langfuse") as mock_langfuse, \
         patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):

        mock_client = AsyncMock()
        mock_instructor.from_anthropic.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=mock_result)

        mock_span = MagicMock()
        mock_langfuse.return_value.span.return_value = mock_span

        result = await critique_persona_node(persona_state)

    assert "critique_results" in result
    assert isinstance(result["critique_results"], list)
    assert len(result["critique_results"]) == 1


@pytest.mark.asyncio
async def test_critique_persona_node_persona_id_matches():
    """The persona_id in the returned CritiqueResult must match what was sent via Send()."""
    persona_state = {
        "persona_id": "recruiter",
        "latex_output": _LATEX_OUTPUT,
        "jd_raw": "Python experience required.",
        "jd_compressed": None,
        "latex_analysis": None,
        "langfuse_trace_id": None,
    }
    # Simulate LLM returning wrong persona_id — node must override it
    wrong_id_result = _SAMPLE_CRITIQUE.model_copy(update={"persona_id": "wrong_id"})

    with patch("pipeline.nodes.critique.instructor") as mock_instructor, \
         patch("pipeline.nodes.critique.anthropic"), \
         patch("pipeline.nodes.critique.Langfuse") as mock_langfuse, \
         patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):

        mock_client = AsyncMock()
        mock_instructor.from_anthropic.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=wrong_id_result)
        mock_langfuse.return_value.span.return_value = MagicMock()

        result = await critique_persona_node(persona_state)

    assert result["critique_results"][0].persona_id == "recruiter"


@pytest.mark.asyncio
async def test_critique_persona_node_slop_detected_on_sloppy_resume():
    """ai_slop_detected should be True when 3+ slop phrases appear in latex."""
    sloppy_latex = LaTeXOutput(
        full_latex=(
            r"\begin{document}"
            r"\item Spearheaded cross-functional collaboration and championed thought leader initiatives."
            r"\end{document}"
        ),
        format_used="STAR",
        word_count=20,
        ats_score_estimate=50,
    )
    persona_state = {
        "persona_id": "recruiter",
        "latex_output": sloppy_latex,
        "jd_raw": "Python required.",
        "jd_compressed": None,
        "latex_analysis": None,
        "langfuse_trace_id": None,
    }
    clean_result = _SAMPLE_CRITIQUE.model_copy(update={"ai_slop_detected": False})

    with patch("pipeline.nodes.critique.instructor") as mock_instructor, \
         patch("pipeline.nodes.critique.anthropic"), \
         patch("pipeline.nodes.critique.Langfuse") as mock_langfuse, \
         patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):

        mock_client = AsyncMock()
        mock_instructor.from_anthropic.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=clean_result)
        mock_langfuse.return_value.span.return_value = MagicMock()

        result = await critique_persona_node(persona_state)

    # Belt-and-suspenders check should override LLM's False
    assert result["critique_results"][0].ai_slop_detected is True


@pytest.mark.asyncio
async def test_critique_persona_node_unknown_persona_raises():
    """FileNotFoundError should propagate when persona .md file is missing."""
    persona_state = {
        "persona_id": "nonexistent_persona_xyz",
        "latex_output": _LATEX_OUTPUT,
        "jd_raw": "Python required.",
        "jd_compressed": None,
        "latex_analysis": None,
        "langfuse_trace_id": None,
    }
    with pytest.raises(FileNotFoundError):
        await critique_persona_node(persona_state)


@pytest.mark.asyncio
async def test_critique_persona_node_no_latex_output_returns_zero_score():
    """When latex_output is None, node returns a score-0 CritiqueResult without calling LLM."""
    persona_state = {
        "persona_id": "recruiter",
        "latex_output": None,
        "jd_raw": "Python required.",
        "jd_compressed": None,
        "latex_analysis": None,
        "langfuse_trace_id": None,
    }
    with patch("pipeline.nodes.critique.Langfuse") as mock_langfuse:
        mock_langfuse.return_value.span.return_value = MagicMock()
        result = await critique_persona_node(persona_state)

    assert result["critique_results"][0].score == 0
    assert result["critique_results"][0].persona_id == "recruiter"


@pytest.mark.asyncio
async def test_critique_persona_node_llm_failure_returns_error_flag():
    """On LLM exception, node returns a CritiqueResult with error flag instead of raising."""
    persona_state = {
        "persona_id": "recruiter",
        "latex_output": _LATEX_OUTPUT,
        "jd_raw": "Python required.",
        "jd_compressed": None,
        "latex_analysis": None,
        "langfuse_trace_id": None,
    }

    with patch("pipeline.nodes.critique.instructor") as mock_instructor, \
         patch("pipeline.nodes.critique.anthropic"), \
         patch("pipeline.nodes.critique.Langfuse") as mock_langfuse, \
         patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):

        mock_client = AsyncMock()
        mock_instructor.from_anthropic.return_value = mock_client
        mock_client.messages.create = AsyncMock(side_effect=RuntimeError("API down"))
        mock_langfuse.return_value.span.return_value = MagicMock()

        result = await critique_persona_node(persona_state)

    cr = result["critique_results"][0]
    assert cr.score == 0
    assert any("error" in f.lower() or "API down" in f for f in cr.flags)
