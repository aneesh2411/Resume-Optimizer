"""
Tests for compress_latex_node.

No LLM calls — pure regex compression.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from pipeline.nodes.compress_latex import compress_latex_node, _compress
from pipeline.schemas import GraphState, LaTeXOutput


_LATEX_OUTPUT = LaTeXOutput(
    full_latex=r"\begin{document}hello\end{document}",
    format_used="STAR",
    word_count=50,
    ats_score_estimate=70,
)


def _make_state(**overrides) -> GraphState:
    base: GraphState = {
        "jd_raw": "Python required.",
        "latex_input": r"\begin{document}hello\end{document}",
        "selected_persona_ids": ["recruiter"],
        "cache_hit": False,
        "compression_attempts": 0,
        "overflow_error": False,
        "critique_results": [],
        "latex_output": _LATEX_OUTPUT,
    }
    base.update(overrides)
    return base


# ── _compress helper ──────────────────────────────────────────────────────────

def test_compress_replaces_vspace():
    latex = r"\vspace{12pt} text \vspace{0.5cm} more"
    result = _compress(latex, 1)
    assert r"\vspace{-2pt}" in result
    assert r"\vspace{12pt}" not in result


def test_compress_replaces_itemsep():
    latex = r"\itemsep3pt text"
    result = _compress(latex, 1)
    assert r"\itemsep -1pt " in result


def test_compress_attempt2_shrinks_fontsize_11():
    latex = r"\fontsize{11} text"
    result = _compress(latex, 2)
    assert r"\fontsize{10.5}" in result


def test_compress_attempt2_shrinks_fontsize_10():
    latex = r"\fontsize{10} text"
    result = _compress(latex, 2)
    assert r"\fontsize{9.5}" in result


def test_compress_attempt1_does_not_shrink_fontsize():
    latex = r"\fontsize{11} text"
    result = _compress(latex, 1)
    # Font shrink only on attempt >= 2
    assert r"\fontsize{11}" in result
    assert r"\fontsize{10.5}" not in result


# ── compress_latex_node ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_compress_first_attempt_returns_compressed_latex():
    latex = r"\begin{document}\vspace{12pt}hello\end{document}"
    state = _make_state(latex_output=LaTeXOutput(
        full_latex=latex,
        format_used="STAR",
        word_count=50,
        ats_score_estimate=70,
    ))

    with patch("pipeline.nodes.compress_latex.Langfuse") as mock_lf:
        mock_lf.return_value.span.return_value = MagicMock()
        result = await compress_latex_node(state)

    assert result["compression_attempts"] == 1
    assert r"\vspace{-2pt}" in result["edited_latex"]
    assert result.get("overflow_error") is not True


@pytest.mark.asyncio
async def test_compress_second_attempt_increments_count():
    latex = r"\begin{document}\vspace{12pt}hello\end{document}"
    state = _make_state(
        compression_attempts=1,
        latex_output=LaTeXOutput(
            full_latex=latex,
            format_used="STAR",
            word_count=50,
            ats_score_estimate=70,
        ),
    )

    with patch("pipeline.nodes.compress_latex.Langfuse") as mock_lf:
        mock_lf.return_value.span.return_value = MagicMock()
        result = await compress_latex_node(state)

    assert result["compression_attempts"] == 2
    assert "edited_latex" in result


@pytest.mark.asyncio
async def test_compress_third_attempt_sets_overflow_error():
    """After 2 compressions (attempts becomes 3), overflow_error must be True."""
    state = _make_state(compression_attempts=2)

    with patch("pipeline.nodes.compress_latex.Langfuse") as mock_lf:
        mock_lf.return_value.span.return_value = MagicMock()
        result = await compress_latex_node(state)

    assert result["overflow_error"] is True
    assert result["compression_attempts"] == 3
    # No edited_latex returned when overflow
    assert "edited_latex" not in result


@pytest.mark.asyncio
async def test_compress_uses_edited_latex_if_present():
    """If edited_latex already exists in state, it should be further compressed."""
    edited = r"\begin{document}\vspace{5pt}edited\end{document}"
    state = _make_state(edited_latex=edited)

    with patch("pipeline.nodes.compress_latex.Langfuse") as mock_lf:
        mock_lf.return_value.span.return_value = MagicMock()
        result = await compress_latex_node(state)

    assert r"\vspace{-2pt}" in result["edited_latex"]
