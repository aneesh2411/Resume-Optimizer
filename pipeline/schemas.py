"""
schemas.py — Single source of truth for all Pydantic data contracts.

Every other Python module in the pipeline imports from here.
All LLM outputs are validated through these models via Instructor.
GraphState is TypedDict (required for LangGraph Send() fan-out with
Annotated[list, operator.add] accumulators).
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, Optional, TypedDict

from pydantic import BaseModel, Field


# ── LaTeX section ─────────────────────────────────────────────────────────────

class LaTeXSection(BaseModel):
    """A named section within the generated LaTeX document."""

    name: str
    content: str = Field(..., max_length=2000)


# ── Primary LaTeX output ──────────────────────────────────────────────────────

class LaTeXOutput(BaseModel):
    """
    Structured LaTeX document produced by generate_node.

    Constraints:
    - full_latex must contain \\begin{document}
    - word_count hard cap of 600 (single-page budget)
    - ats_score_estimate 0–100
    """

    full_latex: str = Field(..., description="Complete LaTeX document including preamble and \\begin{document}...\\end{document}")
    sections: list[LaTeXSection] = Field(default_factory=list)
    format_used: Literal["STAR", "XYZ", "CAR"]
    ats_score_estimate: int = Field(..., ge=0, le=100)
    word_count: int = Field(..., ge=0, le=600)

    def model_post_init(self, __context: Any) -> None:
        if "\\begin{document}" not in self.full_latex:
            raise ValueError("full_latex must contain \\begin{document}")


# ── LaTeX analysis ────────────────────────────────────────────────────────────

class LaTeXAnalysis(TypedDict, total=False):
    """Pure-regex structural analysis of the input LaTeX document."""

    total_bullets: int
    avg_bullet_words: float
    section_count: int
    total_words: int
    sections: list[str]
    keyword_gaps: list[str]


# ── Critique ──────────────────────────────────────────────────────────────────

class CritiqueResult(BaseModel):
    """Output from one critique persona agent."""

    persona_id: str
    score: int = Field(..., ge=0, le=100)
    flags: list[str] = Field(default_factory=list, max_length=10)
    suggestions: list[str] = Field(default_factory=list, max_length=10)
    ai_slop_detected: bool
    jd_match_confidence: int = Field(..., ge=0, le=100)


# ── Debate ────────────────────────────────────────────────────────────────────

class DebateRound(BaseModel):
    """One persona's response to another persona's critique flags."""

    responding_persona_id: str
    responding_to_persona_ids: list[str]
    agreements: list[str] = Field(default_factory=list)
    disagreements: list[str] = Field(default_factory=list)
    synthesis: str = Field(..., max_length=500)


class DebateConsensus(BaseModel):
    """Synthesised consensus produced after all debate rounds."""

    blocking_issues: list[str] = Field(default_factory=list)
    optional_improvements: list[str] = Field(default_factory=list)
    consensus_score: int = Field(..., ge=0, le=100)
    summary: str = Field(..., max_length=1000)


# ── LangGraph state ───────────────────────────────────────────────────────────

class GraphState(TypedDict, total=False):
    """
    LangGraph state passed between nodes.

    TypedDict is required for Send() fan-out: critique_results uses
    Annotated[list[CritiqueResult], operator.add] so each fan-out worker
    appends its single result and LangGraph merges them automatically.
    All nodes must return plain dicts of changed keys only.
    """

    # Inputs
    jd_raw: str
    latex_input: str
    selected_persona_ids: list[str]

    # JD processing
    jd_compressed: Optional[str]
    jd_embedding: Optional[list[float]]
    jd_hash: Optional[str]
    cache_hit: bool

    # Analysis
    latex_analysis: Optional[LaTeXAnalysis]

    # LLM outputs
    latex_output: Optional[LaTeXOutput]
    critique_results: Annotated[list[CritiqueResult], operator.add]
    consensus: Optional[DebateConsensus]

    # HITL
    human_decision: Optional[Literal["regen", "approve", "edit"]]
    edited_latex: Optional[str]

    # Compilation
    pdf_url: Optional[str]
    page_count: Optional[int]
    compile_error: Optional[str]
    compression_attempts: int
    overflow_error: bool

    # Meta
    error: Optional[str]
    langfuse_trace_id: Optional[str]
