"""
human_review_node — interrupt()-based human-in-the-loop node.

The graph pauses here and checkpoints state. The frontend receives the
current latex + consensus payload via the SSE stream's final [DONE] event.

To resume the graph the frontend POSTs to /generate with the same thread_id
and a Command(resume={"decision": ..., "edited_latex": ...}) payload.

Routing after resume:
  "regen"   → generate_node  (re-run generation with blocking issues prepended)
  "approve" → compile_node   (compile the current latex_output)
  "edit"    → compile_node   (compile the edited_latex supplied by the user)
"""

from __future__ import annotations

import logging

from langfuse import Langfuse
from langgraph.types import interrupt

from pipeline.schemas import GraphState

logger = logging.getLogger(__name__)


async def human_review_node(state: GraphState) -> dict:
    """
    Pause graph execution and present the current latex + consensus to the user.

    Returns {"human_decision": str, "edited_latex": str | None}.
    """
    latex_output = state.get("latex_output")
    consensus = state.get("consensus")

    # Build the interrupt payload that the frontend will receive
    interrupt_payload: dict = {
        "latex": getattr(latex_output, "full_latex", None) if latex_output else None,
        "consensus": consensus.model_dump() if consensus else None,
        "critique_results": [c.model_dump() for c in state.get("critique_results", [])],
    }

    lf = Langfuse()
    span = lf.span(
        trace_id=state.get("langfuse_trace_id"),
        name="human_review",
        metadata={"has_consensus": consensus is not None},
    )

    # Pause graph — resumes when Command(resume={...}) is posted by the frontend
    human_input: dict = interrupt(interrupt_payload)

    decision: str = human_input.get("decision", "approve")
    edited_latex: str | None = human_input.get("edited_latex")

    span.update(metadata={"human_decision": decision})
    span.end()

    return {"human_decision": decision, "edited_latex": edited_latex}


def route_after_human(state: GraphState) -> str:
    """
    Routing function called after human_review_node resumes.

    "regen"          → "generate_node"
    "approve"/"edit" → "compile_node"
    """
    decision = state.get("human_decision")
    if decision == "regen":
        return "generate_node"
    return "compile_node"
