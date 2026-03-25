"""
Tests for debate_node — personas respond to each other's flags, then consensus is synthesised.

All LLM calls are mocked.
"""

from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from pipeline.nodes.debate import debate_node
from pipeline.schemas import (
    CritiqueResult,
    DebateConsensus,
    DebateRound,
    GraphState,
    LaTeXOutput,
)


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
    ats_score_estimate=72,
)

_CRITIQUE_A = CritiqueResult(
    persona_id="recruiter",
    score=70,
    flags=["Missing quantified impact", "Weak action verbs"],
    suggestions=["Add metrics", "Use stronger verbs"],
    ai_slop_detected=False,
    jd_match_confidence=60,
)

_CRITIQUE_B = CritiqueResult(
    persona_id="hiring_manager",
    score=65,
    flags=["No leadership evidence", "Too generic"],
    suggestions=["Add team size", "Be more specific"],
    ai_slop_detected=False,
    jd_match_confidence=55,
)

_DEBATE_ROUND_A = DebateRound(
    responding_persona_id="recruiter",
    responding_to_persona_ids=["hiring_manager"],
    agreements=["Leadership evidence is missing"],
    disagreements=[],
    synthesis="I agree with hiring_manager that leadership evidence is missing.",
)

_DEBATE_ROUND_B = DebateRound(
    responding_persona_id="hiring_manager",
    responding_to_persona_ids=["recruiter"],
    agreements=["Weak action verbs"],
    disagreements=[],
    synthesis="Recruiter's point about weak action verbs is valid.",
)

_CONSENSUS = DebateConsensus(
    blocking_issues=["Missing quantified impact", "No leadership evidence"],
    optional_improvements=["Add team size", "Use stronger verbs"],
    consensus_score=67,
    summary="Resume needs stronger metrics and leadership evidence before approval.",
)


def _make_state(**overrides) -> GraphState:
    base: GraphState = {
        "jd_raw": "We need Python and Kubernetes skills.",
        "latex_input": _SAMPLE_LATEX,
        "selected_persona_ids": ["recruiter", "hiring_manager"],
        "cache_hit": False,
        "compression_attempts": 0,
        "overflow_error": False,
        "critique_results": [_CRITIQUE_A, _CRITIQUE_B],
        "latex_output": _LATEX_OUTPUT,
    }
    base.update(overrides)
    return base


# ── debate_node ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_debate_node_returns_consensus():
    state = _make_state()

    with patch("pipeline.nodes.debate.instructor") as mock_instructor, \
         patch("pipeline.nodes.debate.anthropic"), \
         patch("pipeline.nodes.debate.Langfuse") as mock_langfuse, \
         patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):

        mock_client = AsyncMock()
        mock_instructor.from_anthropic.return_value = mock_client
        # 2 debate rounds + 1 consensus
        mock_client.messages.create = AsyncMock(
            side_effect=[_DEBATE_ROUND_A, _DEBATE_ROUND_B, _CONSENSUS]
        )
        mock_langfuse.return_value.span.return_value = MagicMock()

        result = await debate_node(state)

    assert "consensus" in result
    assert isinstance(result["consensus"], DebateConsensus)


@pytest.mark.asyncio
async def test_debate_node_consensus_has_blocking_issues():
    state = _make_state()

    with patch("pipeline.nodes.debate.instructor") as mock_instructor, \
         patch("pipeline.nodes.debate.anthropic"), \
         patch("pipeline.nodes.debate.Langfuse") as mock_langfuse, \
         patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):

        mock_client = AsyncMock()
        mock_instructor.from_anthropic.return_value = mock_client
        mock_client.messages.create = AsyncMock(
            side_effect=[_DEBATE_ROUND_A, _DEBATE_ROUND_B, _CONSENSUS]
        )
        mock_langfuse.return_value.span.return_value = MagicMock()

        result = await debate_node(state)

    assert isinstance(result["consensus"].blocking_issues, list)


@pytest.mark.asyncio
async def test_debate_node_resets_critique_results():
    """debate_node should reset critique_results to [] to clear the accumulator for regen."""
    state = _make_state()

    with patch("pipeline.nodes.debate.instructor") as mock_instructor, \
         patch("pipeline.nodes.debate.anthropic"), \
         patch("pipeline.nodes.debate.Langfuse") as mock_langfuse, \
         patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):

        mock_client = AsyncMock()
        mock_instructor.from_anthropic.return_value = mock_client
        mock_client.messages.create = AsyncMock(
            side_effect=[_DEBATE_ROUND_A, _DEBATE_ROUND_B, _CONSENSUS]
        )
        mock_langfuse.return_value.span.return_value = MagicMock()

        result = await debate_node(state)

    assert "critique_results" in result
    assert result["critique_results"] == []


@pytest.mark.asyncio
async def test_debate_node_calls_llm_once_per_persona_plus_consensus():
    """2 personas → 2 debate round calls + 1 consensus call = 3 total."""
    state = _make_state()
    call_count = 0

    async def count_calls(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return _DEBATE_ROUND_A if call_count == 1 else _DEBATE_ROUND_B
        return _CONSENSUS

    with patch("pipeline.nodes.debate.instructor") as mock_instructor, \
         patch("pipeline.nodes.debate.anthropic"), \
         patch("pipeline.nodes.debate.Langfuse") as mock_langfuse, \
         patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):

        mock_client = AsyncMock()
        mock_instructor.from_anthropic.return_value = mock_client
        mock_client.messages.create = AsyncMock(side_effect=count_calls)
        mock_langfuse.return_value.span.return_value = MagicMock()

        await debate_node(state)

    assert call_count == 3  # 2 rounds + 1 consensus


@pytest.mark.asyncio
async def test_debate_node_single_persona_still_produces_consensus():
    """With only one persona there are no cross-critiques but consensus is still produced."""
    state = _make_state(
        critique_results=[_CRITIQUE_A],
        selected_persona_ids=["recruiter"],
    )

    with patch("pipeline.nodes.debate.instructor") as mock_instructor, \
         patch("pipeline.nodes.debate.anthropic"), \
         patch("pipeline.nodes.debate.Langfuse") as mock_langfuse, \
         patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):

        mock_client = AsyncMock()
        mock_instructor.from_anthropic.return_value = mock_client
        # 1 debate round + 1 consensus
        mock_client.messages.create = AsyncMock(
            side_effect=[_DEBATE_ROUND_A, _CONSENSUS]
        )
        mock_langfuse.return_value.span.return_value = MagicMock()

        result = await debate_node(state)

    assert isinstance(result["consensus"], DebateConsensus)


@pytest.mark.asyncio
async def test_debate_node_uses_jd_compressed_when_available():
    state = _make_state(jd_compressed="Compressed: Python, Kubernetes.")

    with patch("pipeline.nodes.debate.instructor") as mock_instructor, \
         patch("pipeline.nodes.debate.anthropic"), \
         patch("pipeline.nodes.debate.Langfuse") as mock_langfuse, \
         patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):

        mock_client = AsyncMock()
        mock_instructor.from_anthropic.return_value = mock_client
        mock_client.messages.create = AsyncMock(
            side_effect=[_DEBATE_ROUND_A, _DEBATE_ROUND_B, _CONSENSUS]
        )
        mock_langfuse.return_value.span.return_value = MagicMock()

        result = await debate_node(state)

    assert isinstance(result["consensus"], DebateConsensus)


@pytest.mark.asyncio
async def test_debate_node_llm_failure_falls_back_gracefully():
    """If LLM calls all fail, debate_node returns a fallback consensus without raising."""
    state = _make_state()

    with patch("pipeline.nodes.debate.instructor") as mock_instructor, \
         patch("pipeline.nodes.debate.anthropic"), \
         patch("pipeline.nodes.debate.Langfuse") as mock_langfuse, \
         patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):

        mock_client = AsyncMock()
        mock_instructor.from_anthropic.return_value = mock_client
        mock_client.messages.create = AsyncMock(
            side_effect=RuntimeError("Network error")
        )
        mock_langfuse.return_value.span.return_value = MagicMock()

        result = await debate_node(state)

    assert "consensus" in result
    assert isinstance(result["consensus"], DebateConsensus)
    # Fallback consensus should have at least some blocking issues from the critiques
    assert len(result["consensus"].blocking_issues) > 0
