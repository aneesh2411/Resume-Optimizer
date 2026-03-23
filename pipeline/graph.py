"""
graph.py — LangGraph stateful agent graph definition.

Graph topology:
  [START]
     │
  [ingest]         — sanitise + truncate inputs
     │
  [compress]       — LLMLingua-2 JD compression
     │
  [embed_and_cache] — SHA-256 exact match → pgvector semantic match (cos ≥ 0.92)
     │                on cache hit: skip directly to resolve
     ▼              on cache miss: proceed to generate
  [generate]       — Claude claude-sonnet-4-6 via Instructor → ResumeOutput
     │
  [critique]       — parallel: recruiter + hiring_manager + expert (asyncio.gather)
     │
  [resolve]        — synthesise 3 CritiqueResults → ConflictResolution
     │
     ┤ ← INTERRUPT BEFORE "iterate" (HITL: user sees critique, chooses to accept or refine)
     │
  [iterate]        — clear previous outputs, prepare next pass
     │
  [generate]       — re-enter generate with user_iteration_feedback
     │
  ... (loops up to max_iterations times)
     │
  [END]

The HITL interrupt is implemented via LangGraph's interrupt_before mechanism.
When paused, the frontend receives the current GraphState via SSE and presents
the critique to the user. The user submits feedback (or approves), and the
/api/generate route resumes the graph via the checkpointer thread.
"""

from __future__ import annotations

import logging

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from pipeline.nodes.cache import embed_and_cache_node
from pipeline.nodes.compress import compress_node
from pipeline.nodes.critique import parallel_critique_node
from pipeline.nodes.generate import generate_node
from pipeline.nodes.ingest import ingest_node
from pipeline.nodes.iterate import iterate_node
from pipeline.nodes.resolve import join_and_resolve_node
from pipeline.schemas import GraphState

logger = logging.getLogger(__name__)


# ── Routing functions ─────────────────────────────────────────────────────────

def route_after_cache(state: GraphState) -> str:
    """After embed_and_cache: skip to resolve if cache hit, else generate."""
    if state.cache_hit and state.critique_results:
        return "resolve"
    if state.cache_hit:
        return "generate"  # have resume but no critiques — run critique
    return "generate"


def route_after_resolve(state: GraphState) -> str:
    """
    After resolve: check if the user approved or max iterations reached.
    On first pass this always goes to END (HITL interrupt fires before 'iterate').
    On resume with feedback: either iterate again or end.
    """
    if state.error:
        return END  # type: ignore[return-value]
    if state.approved or state.iteration_count >= state.max_iterations:
        return END  # type: ignore[return-value]
    return "iterate"


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    builder: StateGraph = StateGraph(GraphState)

    # ── Nodes ─────────────────────────────────────────────────────────────────
    builder.add_node("ingest", ingest_node)
    builder.add_node("compress", compress_node)
    builder.add_node("embed_and_cache", embed_and_cache_node)
    builder.add_node("generate", generate_node)
    builder.add_node("critique", parallel_critique_node)
    builder.add_node("resolve", join_and_resolve_node)
    builder.add_node("iterate", iterate_node)

    # ── Entry point ───────────────────────────────────────────────────────────
    builder.set_entry_point("ingest")

    # ── Edges ─────────────────────────────────────────────────────────────────
    builder.add_edge("ingest", "compress")
    builder.add_edge("compress", "embed_and_cache")

    # Conditional: cache hit can skip generate+critique
    builder.add_conditional_edges(
        "embed_and_cache",
        route_after_cache,
        {
            "generate": "generate",
            "resolve": "resolve",
        },
    )

    builder.add_edge("generate", "critique")
    builder.add_edge("critique", "resolve")

    # Conditional after resolve: iterate (with HITL) or end
    builder.add_conditional_edges(
        "resolve",
        route_after_resolve,
        {
            "iterate": "iterate",
            END: END,
        },
    )

    # iterate → generate loop
    builder.add_edge("iterate", "generate")

    # ── Compile with HITL interrupt ───────────────────────────────────────────
    # The graph pauses before executing "iterate" — this is the HITL checkpoint.
    # The frontend receives the full state (resume + critique) and the user
    # decides to approve or submit feedback. On resume, user_iteration_feedback
    # and approved are set on the state before re-entering.
    checkpointer = MemorySaver()  # swap to Redis checkpointer for multi-worker prod
    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["iterate"],
    )


# Module-level singleton
graph = build_graph()
