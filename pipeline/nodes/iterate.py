"""
iterate_node — prepare state for the next generation pass.

This is a thin router that:
1. Increments the iteration count
2. Clears the previous resume output and critique results so generate_node
   runs fresh with the user's new feedback
3. Sets cache_hit = False to force a new LLM call (feedback changed the context)

The actual regeneration is handled by re-entering generate_node.
"""

from __future__ import annotations

from pipeline.schemas import GraphState


async def iterate_node(state: GraphState) -> GraphState:
    """Reset pipeline outputs and prepare for the next generate pass."""
    return state.model_copy(
        update={
            "cache_hit": False,          # force fresh LLM call
            "resume_output": None,       # clear previous output
            "critique_results": [],      # clear previous critiques
            "conflict_resolution": None, # clear previous resolution
        }
    )
