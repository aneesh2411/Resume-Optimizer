"""
Tests for compile_node and route_after_compile.

httpx is mocked so no real HTTP calls are made.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from pipeline.nodes.compile import compile_node, route_after_compile
from pipeline.schemas import (
    CritiqueResult,
    DebateConsensus,
    GraphState,
    LaTeXOutput,
)

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


def _mock_compile_response(success: bool, pdf_url: str | None = None, page_count: int = 1, error: str | None = None) -> dict:
    return {
        "job_id": "test-job-id",
        "success": success,
        "pdf_url": pdf_url,
        "page_count": page_count,
        "error": error,
    }


# ── compile_node tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_compile_node_success_single_page():
    state = _make_state()
    response_data = _mock_compile_response(True, "https://example.com/resume.pdf", page_count=1)

    mock_response = MagicMock()
    mock_response.json.return_value = response_data
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_client)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    with patch("pipeline.nodes.compile.httpx.AsyncClient", return_value=mock_context), \
         patch("pipeline.nodes.compile.Langfuse") as mock_lf:
        mock_lf.return_value.span.return_value = MagicMock()
        result = await compile_node(state)

    assert result["pdf_url"] == "https://example.com/resume.pdf"
    assert result["page_count"] == 1
    assert result["compile_error"] is None


@pytest.mark.asyncio
async def test_compile_node_success_multi_page():
    state = _make_state()
    response_data = _mock_compile_response(True, "https://example.com/resume.pdf", page_count=2)

    mock_response = MagicMock()
    mock_response.json.return_value = response_data
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_client)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    with patch("pipeline.nodes.compile.httpx.AsyncClient", return_value=mock_context), \
         patch("pipeline.nodes.compile.Langfuse") as mock_lf:
        mock_lf.return_value.span.return_value = MagicMock()
        result = await compile_node(state)

    assert result["page_count"] == 2
    assert result["compile_error"] is None


@pytest.mark.asyncio
async def test_compile_node_compile_failure():
    state = _make_state()
    response_data = _mock_compile_response(False, error="Undefined control sequence \\foo")

    mock_response = MagicMock()
    mock_response.json.return_value = response_data
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_client)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    with patch("pipeline.nodes.compile.httpx.AsyncClient", return_value=mock_context), \
         patch("pipeline.nodes.compile.Langfuse") as mock_lf:
        mock_lf.return_value.span.return_value = MagicMock()
        result = await compile_node(state)

    assert result["compile_error"] == "Undefined control sequence \\foo"
    assert result["page_count"] == 0


@pytest.mark.asyncio
async def test_compile_node_http_exception():
    state = _make_state()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))
    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_client)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    with patch("pipeline.nodes.compile.httpx.AsyncClient", return_value=mock_context), \
         patch("pipeline.nodes.compile.Langfuse") as mock_lf:
        mock_lf.return_value.span.return_value = MagicMock()
        result = await compile_node(state)

    assert "Connection refused" in result["compile_error"]
    assert result["page_count"] == 0


@pytest.mark.asyncio
async def test_compile_node_uses_edited_latex_when_present():
    """compile_node should use edited_latex instead of latex_output.full_latex."""
    edited = r"\begin{document}edited\end{document}"
    state = _make_state(edited_latex=edited)
    response_data = _mock_compile_response(True, "https://example.com/resume.pdf", page_count=1)

    posted_body = {}

    async def capture_post(url, json=None, **kwargs):
        posted_body.update(json or {})
        mock_resp = MagicMock()
        mock_resp.json.return_value = response_data
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    mock_client = AsyncMock()
    mock_client.post = capture_post
    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_client)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    with patch("pipeline.nodes.compile.httpx.AsyncClient", return_value=mock_context), \
         patch("pipeline.nodes.compile.Langfuse") as mock_lf:
        mock_lf.return_value.span.return_value = MagicMock()
        await compile_node(state)

    assert posted_body["latex_content"] == edited


# ── route_after_compile tests ─────────────────────────────────────────────────

def test_route_compile_error_goes_to_end():
    from langgraph.graph import END
    state = _make_state(compile_error="some error", page_count=0)
    assert route_after_compile(state) == END


def test_route_overflow_error_goes_to_end():
    from langgraph.graph import END
    state = _make_state(overflow_error=True, page_count=2)
    assert route_after_compile(state) == END


def test_route_multi_page_goes_to_compress():
    state = _make_state(page_count=2)
    assert route_after_compile(state) == "compress_latex_node"


def test_route_single_page_goes_to_cache():
    state = _make_state(page_count=1)
    assert route_after_compile(state) == "cache_and_store_node"


def test_route_zero_page_count_goes_to_cache():
    """Zero page count (unknown) should not trigger compression."""
    state = _make_state(page_count=0)
    assert route_after_compile(state) == "cache_and_store_node"
