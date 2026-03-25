"""
Tests for pipeline nodes (without LLM calls — pure unit tests).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from pipeline.nodes.ingest import ingest_node, _get_known_persona_ids
from pipeline.schemas import GraphState


_VALID_LATEX = r"""\documentclass{article}
\begin{document}
\section{Experience}
\begin{itemize}
\item Built Python services handling 50k req/s.
\end{itemize}
\end{document}"""

_VALID_JD = "We are looking for a senior software engineer with 5+ years Python experience in distributed systems."


def _state(**overrides) -> GraphState:
    base: GraphState = {
        "jd_raw": _VALID_JD,
        "latex_input": _VALID_LATEX,
        "selected_persona_ids": ["faang_bar_raiser"],
        "cache_hit": False,
        "compression_attempts": 0,
        "overflow_error": False,
        "critique_results": [],
    }
    base.update(overrides)
    return base


# ── ingest_node ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ingest_node_passes_valid_inputs(tmp_path, monkeypatch):
    """Valid JD + LaTeX + known persona IDs → returns dict with cleaned values."""
    personas_dir = tmp_path / "personas"
    personas_dir.mkdir()
    (personas_dir / "faang_bar_raiser.md").write_text("# FAANG Bar Raiser")

    with patch("pipeline.nodes.ingest._PERSONAS_DIR", personas_dir):
        result = await ingest_node(_state())

    assert result.get("error") is None
    assert result["jd_raw"].startswith("We are looking")
    assert "\\begin{document}" in result["latex_input"]
    assert result["selected_persona_ids"] == ["faang_bar_raiser"]


@pytest.mark.asyncio
async def test_ingest_node_rejects_short_jd(tmp_path, monkeypatch):
    personas_dir = tmp_path / "personas"
    personas_dir.mkdir()
    (personas_dir / "faang_bar_raiser.md").write_text("# FAANG Bar Raiser")

    with patch("pipeline.nodes.ingest._PERSONAS_DIR", personas_dir):
        result = await ingest_node(_state(jd_raw="Too short"))

    assert result.get("error") is not None
    assert "too short" in result["error"].lower()


@pytest.mark.asyncio
async def test_ingest_node_truncates_long_jd(tmp_path):
    long_jd = "software engineer " * 600  # >> 8000 chars
    personas_dir = tmp_path / "personas"
    personas_dir.mkdir()
    (personas_dir / "faang_bar_raiser.md").write_text("# FAANG Bar Raiser")

    with patch("pipeline.nodes.ingest._PERSONAS_DIR", personas_dir):
        result = await ingest_node(_state(jd_raw=long_jd))

    assert result.get("error") is None
    assert len(result["jd_raw"]) <= 8000


@pytest.mark.asyncio
async def test_ingest_node_rejects_missing_begin_document(tmp_path):
    bad_latex = r"\documentclass{article}% no begin document here"
    personas_dir = tmp_path / "personas"
    personas_dir.mkdir()
    (personas_dir / "faang_bar_raiser.md").write_text("# FAANG Bar Raiser")

    with patch("pipeline.nodes.ingest._PERSONAS_DIR", personas_dir):
        result = await ingest_node(_state(latex_input=bad_latex))

    assert result.get("error") is not None
    assert "latex" in result["error"].lower()


@pytest.mark.asyncio
async def test_ingest_node_rejects_unknown_persona_ids(tmp_path):
    personas_dir = tmp_path / "personas"
    personas_dir.mkdir()
    (personas_dir / "faang_bar_raiser.md").write_text("# FAANG Bar Raiser")

    with patch("pipeline.nodes.ingest._PERSONAS_DIR", personas_dir):
        result = await ingest_node(_state(selected_persona_ids=["faang_bar_raiser", "ghost_persona"]))

    assert result.get("error") is not None
    assert "ghost_persona" in result["error"]


@pytest.mark.asyncio
async def test_ingest_node_rejects_empty_persona_ids(tmp_path):
    personas_dir = tmp_path / "personas"
    personas_dir.mkdir()

    with patch("pipeline.nodes.ingest._PERSONAS_DIR", personas_dir):
        result = await ingest_node(_state(selected_persona_ids=[]))

    assert result.get("error") is not None
    assert "persona" in result["error"].lower()


@pytest.mark.asyncio
async def test_ingest_node_strips_null_bytes(tmp_path):
    dirty_jd = "Software\x00 engineer role with Python experience required for distributed systems."
    personas_dir = tmp_path / "personas"
    personas_dir.mkdir()
    (personas_dir / "faang_bar_raiser.md").write_text("# FAANG Bar Raiser")

    with patch("pipeline.nodes.ingest._PERSONAS_DIR", personas_dir):
        result = await ingest_node(_state(jd_raw=dirty_jd))

    assert "\x00" not in result["jd_raw"]


def test_get_known_persona_ids_scans_md_files(tmp_path):
    personas_dir = tmp_path / "personas"
    personas_dir.mkdir()
    (personas_dir / "faang_bar_raiser.md").write_text("# FAANG")
    (personas_dir / "startup_cto.md").write_text("# CTO")
    (personas_dir / "not_a_persona.txt").write_text("ignored")

    with patch("pipeline.nodes.ingest._PERSONAS_DIR", personas_dir):
        ids = _get_known_persona_ids()

    assert "faang_bar_raiser" in ids
    assert "startup_cto" in ids
    assert "not_a_persona" not in ids
