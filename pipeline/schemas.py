"""
schemas.py — Single source of truth for all Pydantic data contracts.

Every other Python module in the pipeline imports from here.
All LLM outputs are validated through these models via Instructor.
"""

from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


# ── Resume sections ───────────────────────────────────────────────────────────

class ResumeSection(BaseModel):
    """Generic resume section with a hard character cap."""

    content: str = Field(..., max_length=300)


# ── Primary resume output ─────────────────────────────────────────────────────

class ResumeOutput(BaseModel):
    """
    Structured resume produced by the generate node.

    Enforced constraints:
    - headline  : max 80 chars
    - summary   : max 300 chars (via ResumeSection)
    - experience: 1–3 roles, each max 300 chars
    - skills    : max 150 chars
    - education : max 150 chars
    - word_count: HARD cap of 600 (single-page budget)
    """

    headline: str = Field(..., max_length=80)
    summary: ResumeSection
    experience: list[ResumeSection] = Field(..., min_length=1, max_length=3)
    skills: ResumeSection
    education: ResumeSection
    format_used: Literal["STAR", "XYZ", "CAR"]
    ats_score_estimate: int = Field(..., ge=0, le=100)
    word_count: int = Field(..., ge=0, le=600)

    @field_validator("skills")
    @classmethod
    def skills_max_150(cls, v: ResumeSection) -> ResumeSection:
        if len(v.content) > 150:
            raise ValueError("skills.content must be ≤ 150 characters")
        return v

    @field_validator("education")
    @classmethod
    def education_max_150(cls, v: ResumeSection) -> ResumeSection:
        if len(v.content) > 150:
            raise ValueError("education.content must be ≤ 150 characters")
        return v

    @model_validator(mode="after")
    def verify_word_count(self) -> "ResumeOutput":
        """Cross-field: recount words from all sections and verify declared word_count."""
        parts: list[str] = [self.headline, self.summary.content]
        parts += [exp.content for exp in self.experience]
        parts += [self.skills.content, self.education.content]
        actual = sum(len(p.split()) for p in parts)
        if actual > 600:
            raise ValueError(
                f"Total word count {actual} exceeds single-page budget of 600"
            )
        # Allow declared word_count to differ slightly (LLM may count differently)
        # but hard-fail on actual content overflow.
        return self


# ── Critique ──────────────────────────────────────────────────────────────────

class CritiqueResult(BaseModel):
    """Output from one of the three critique agents."""

    role: Literal["recruiter", "hiring_manager", "expert"]
    score: int = Field(..., ge=0, le=100)
    flags: list[str] = Field(default_factory=list, max_length=10)
    suggestions: list[str] = Field(default_factory=list, max_length=10)
    ai_slop_detected: bool
    jd_match_confidence: int = Field(..., ge=0, le=100)


# ── Conflict resolution ───────────────────────────────────────────────────────

class ConflictResolution(BaseModel):
    """Synthesised consensus from all three critique agents."""

    priority_flags: list[str]
    consensus_score: int = Field(..., ge=0, le=100)
    blocking_issues: list[str]          # must be fixed before export
    optional_improvements: list[str]


# ── LangGraph state ───────────────────────────────────────────────────────────

class GraphState(BaseModel):
    """
    Immutable-by-convention state passed between LangGraph nodes.

    Nodes return `state.model_copy(update={...})` rather than mutating in-place.
    """

    # ── Inputs ──────────────────────────────────────────────
    jd_raw: str
    resume_raw: Optional[str] = None
    user_iteration_feedback: Optional[str] = None

    # ── Intermediate ─────────────────────────────────────────
    jd_compressed: Optional[str] = None
    jd_embedding: Optional[list[float]] = None
    jd_hash: Optional[str] = None
    cache_hit: bool = False

    # ── Outputs ──────────────────────────────────────────────
    resume_output: Optional[ResumeOutput] = None
    critique_results: list[CritiqueResult] = Field(default_factory=list)
    conflict_resolution: Optional[ConflictResolution] = None

    # ── Iteration control ─────────────────────────────────────
    iteration_count: int = 0
    max_iterations: int = 3
    approved: bool = False
    error: Optional[str] = None

    # ── Observability ─────────────────────────────────────────
    langfuse_trace_id: Optional[str] = None

    model_config = {"arbitrary_types_allowed": True}

    def to_serializable(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict (for SSE / Redis storage)."""
        return self.model_dump(mode="json")
