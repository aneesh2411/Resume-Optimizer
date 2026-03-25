"""
graph.py — LangGraph stateful agent graph definition.

New graph topology:
  [START]
    → ingest_node
    → embed_and_cache_node   (cache hit → END via pdf_url; miss → analyze_latex_node)
    → analyze_latex_node     (pure regex, no LLM)
    → generate_node          (Claude → LaTeXOutput)
    → [Send() fan-out] → critique_persona × N
    → debate_node
    → human_review_node      (interrupt(); regen → generate_node; approve/edit → compile_node)
    → compile_node           (calls /compile-direct; page_count > 1 → compress_latex_node)
    → compress_latex_node    (regex compression; loops back to compile_node; max 2×)
    → cache_and_store_node
    → [END]

LangGraph Send() fan-out:
  fan_out_to_personas() returns list[Send("critique_persona", {...})] — one per
  selected persona ID. critique_results uses Annotated[list, operator.add] so
  each worker's {"critique_results": [result]} is merged automatically.

HITL:
  human_review_node calls interrupt() which raises GraphInterrupt and checkpoints
  state. Frontend resumes by POST /generate with Command(resume={...}).
"""

from __future__ import annotations

import logging

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from pipeline.nodes.analyze_latex import analyze_latex_node
from pipeline.nodes.cache import embed_and_cache_node
from pipeline.nodes.cache_and_store import cache_and_store_node
from pipeline.nodes.compile import compile_node, route_after_compile
from pipeline.nodes.compress_latex import compress_latex_node
from pipeline.nodes.critique import critique_persona_node, fan_out_to_personas
from pipeline.nodes.debate import debate_node
from pipeline.nodes.generate import generate_node
from pipeline.nodes.human_review import human_review_node, route_after_human
from pipeline.nodes.ingest import ingest_node
from pipeline.schemas import GraphState

logger = logging.getLogger(__name__)


# ── Routing: cache hit vs miss ─────────────────────────────────────────────────

def route_after_cache(state: GraphState) -> str:
    """After embed_and_cache_node: skip all LLM work on cache hit."""
    if state.get("cache_hit"):
        return "hit"
    return "miss"


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    builder: StateGraph = StateGraph(GraphState)

    # ── Nodes ─────────────────────────────────────────────────────────────────
    builder.add_node("ingest_node", ingest_node)
    builder.add_node("embed_and_cache_node", embed_and_cache_node)
    builder.add_node("analyze_latex_node", analyze_latex_node)
    builder.add_node("generate_node", generate_node)
    builder.add_node("critique_persona", critique_persona_node)
    builder.add_node("debate_node", debate_node)
    builder.add_node("human_review_node", human_review_node)
    builder.add_node("compile_node", compile_node)
    builder.add_node("compress_latex_node", compress_latex_node)
    builder.add_node("cache_and_store_node", cache_and_store_node)

    # ── Entry point ───────────────────────────────────────────────────────────
    builder.set_entry_point("ingest_node")

    # ── Edges ─────────────────────────────────────────────────────────────────
    builder.add_edge("ingest_node", "embed_and_cache_node")

    # Cache hit → END (pdf_url already in state); miss → analyze + generate
    builder.add_conditional_edges(
        "embed_and_cache_node",
        route_after_cache,
        {"hit": END, "miss": "analyze_latex_node"},
    )

    builder.add_edge("analyze_latex_node", "generate_node")

    # Send() fan-out: generate_node output → N parallel critique_persona workers
    builder.add_conditional_edges(
        "generate_node",
        fan_out_to_personas,
        ["critique_persona"],  # target node name(s) used by Send()
    )

    builder.add_edge("critique_persona", "debate_node")
    builder.add_edge("debate_node", "human_review_node")

    # HITL routing: regen → generate_node; approve/edit → compile_node
    builder.add_conditional_edges(
        "human_review_node",
        route_after_human,
        {
            "generate_node": "generate_node",
            "compile_node": "compile_node",
        },
    )

    # Compile routing: overflow/error → END; multi-page → compress; done → cache
    builder.add_conditional_edges(
        "compile_node",
        route_after_compile,
        {
            "compress_latex_node": "compress_latex_node",
            "cache_and_store_node": "cache_and_store_node",
            END: END,
        },
    )

    # Compression loop back to compile
    builder.add_edge("compress_latex_node", "compile_node")

    # Final storage → done
    builder.add_edge("cache_and_store_node", END)

    # ── Compile with HITL interrupt ───────────────────────────────────────────
    # Graph pauses inside human_review_node via interrupt(). No interrupt_before
    # needed — interrupt() handles the checkpoint internally.
    checkpointer = MemorySaver()  # swap for Redis in multi-worker prod
    return builder.compile(checkpointer=checkpointer)


# Module-level singleton used by main.py and tests
graph = build_graph()
