"""
Tests for human_review_node and route_after_human.

interrupt() is mocked to return a pre-defined human_input dict.
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from pipeline.nodes.human_review import human_review_node, route_after_human
from pipeline.schemas import (
    CritiqueResult,
    DebateConsensus,
    GraphState,
    LaTeXOutput,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

_LATEX_OUTPUT = LaTeXOutput(
    full_latex=r"\begin{document}hello\end{document}",
    format_used="STAR",
    word_count=50,
    ats_score_estimate=70,
)

_CONSENSUS = DebateConsensus(
    blocking_issues=["Missing quantified impact"],
    optional_improvements=["Add team size"],
    consensus_score=68,
    summary="Needs improvement before approval.",
)


def _make_state(**overrides) -> GraphState:
    base: GraphState = {
        "jd_raw": "Python and Kubernetes required.",
        "latex_input": r"\begin{document}hello\end{document}",
        "selected_persona_ids": ["recruiter"],
        "cache_hit": False,
        "compression_attempts": 0,
        "overflow_error": False,
        "critique_results": [],
        "latex_output": _LATEX_OUTPUT,
        "consensus": _CONSENSUS,
    }
    base.update(overrides)
    return base


# ── human_review_node ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_human_review_node_approve_decision():
    state = _make_state()

    with patch("pipeline.nodes.human_review.interrupt") as mock_interrupt, \
         patch("pipeline.nodes.human_review.Langfuse") as mock_langfuse:

        mock_interrupt.return_value = {"decision": "approve"}
        mock_langfuse.return_value.span.return_value = MagicMock()

        result = await human_review_node(state)

    assert result["human_decision"] == "approve"
    assert result.get("edited_latex") is None


@pytest.mark.asyncio
async def test_human_review_node_regen_decision():
    state = _make_state()

    with patch("pipeline.nodes.human_review.interrupt") as mock_interrupt, \
         patch("pipeline.nodes.human_review.Langfuse") as mock_langfuse:

        mock_interrupt.return_value = {"decision": "regen"}
        mock_langfuse.return_value.span.return_value = MagicMock()

        result = await human_review_node(state)

    assert result["human_decision"] == "regen"


@pytest.mark.asyncio
async def test_human_review_node_edit_decision_with_latex():
    edited = r"\begin{document}improved\end{document}"
    state = _make_state()

    with patch("pipeline.nodes.human_review.interrupt") as mock_interrupt, \
         patch("pipeline.nodes.human_review.Langfuse") as mock_langfuse:

        mock_interrupt.return_value = {"decision": "edit", "edited_latex": edited}
        mock_langfuse.return_value.span.return_value = MagicMock()

        result = await human_review_node(state)

    assert result["human_decision"] == "edit"
    assert result["edited_latex"] == edited


@pytest.mark.asyncio
async def test_human_review_node_defaults_to_approve_when_no_decision():
    """If the human input dict has no 'decision' key, default to 'approve'."""
    state = _make_state()

    with patch("pipeline.nodes.human_review.interrupt") as mock_interrupt, \
         patch("pipeline.nodes.human_review.Langfuse") as mock_langfuse:

        mock_interrupt.return_value = {}  # no decision key
        mock_langfuse.return_value.span.return_value = MagicMock()

        result = await human_review_node(state)

    assert result["human_decision"] == "approve"


@pytest.mark.asyncio
async def test_human_review_node_interrupt_receives_latex_and_consensus():
    """interrupt() should be called with current latex and consensus payload."""
    state = _make_state()
    interrupt_payload = {}

    def capture_interrupt(value):
        interrupt_payload.update(value)
        return {"decision": "approve"}

    with patch("pipeline.nodes.human_review.interrupt", side_effect=capture_interrupt), \
         patch("pipeline.nodes.human_review.Langfuse") as mock_langfuse:

        mock_langfuse.return_value.span.return_value = MagicMock()
        await human_review_node(state)

    assert "latex" in interrupt_payload
    assert "consensus" in interrupt_payload


# ── route_after_human ─────────────────────────────────────────────────────────

def test_route_after_human_approve_goes_to_compile():
    state = _make_state(human_decision="approve")
    assert route_after_human(state) == "compile_node"


def test_route_after_human_edit_goes_to_compile():
    state = _make_state(
        human_decision="edit",
        edited_latex=r"\begin{document}edited\end{document}",
    )
    assert route_after_human(state) == "compile_node"


def test_route_after_human_regen_goes_to_generate():
    state = _make_state(human_decision="regen")
    assert route_after_human(state) == "generate_node"


def test_route_after_human_none_decision_goes_to_compile():
    """Unrecognised or None decision defaults to compile."""
    state = _make_state()
    state.pop("human_decision", None)
    assert route_after_human(state) == "compile_node"
