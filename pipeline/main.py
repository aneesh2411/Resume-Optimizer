"""
main.py — FastAPI application serving the LangGraph resume pipeline.

Endpoints:
  POST /generate     — Start or resume a graph run; streams SSE events
  GET  /cache/status — Check if a JD hash has a cached result
  GET  /health       — Liveness probe

Security:
  All routes (except /health) require the X-Pipeline-Secret HMAC header.
  This is a shared secret between Next.js and FastAPI — never expose it to the browser.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langfuse import Langfuse
from pydantic import BaseModel

load_dotenv()  # load .env / .env.local in development

from pipeline.graph import graph  # noqa: E402 (must be after load_dotenv)
from pipeline.nodes.cache import store_cache  # noqa: E402
from pipeline.schemas import GraphState  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Resume Pipeline", version="0.1.0", docs_url="/docs")

# ── CORS ──────────────────────────────────────────────────────────────────────
_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    os.environ.get("NEXT_PUBLIC_APP_URL", "http://localhost:3000"),
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── Auth ──────────────────────────────────────────────────────────────────────

def verify_pipeline_secret(request: Request) -> None:
    """HMAC constant-time comparison of the X-Pipeline-Secret header."""
    secret = os.environ.get("PIPELINE_SECRET", "")
    token = request.headers.get("X-Pipeline-Secret", "")
    if not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="Unauthorised")


# ── Request / response models ─────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    jd_raw: str
    resume_raw: str | None = None
    thread_id: str | None = None
    user_iteration_feedback: str | None = None
    approved: bool = False


# ── SSE streaming ─────────────────────────────────────────────────────────────

async def _stream_graph_events(
    initial_state: GraphState,
    thread_id: str,
) -> AsyncGenerator[str, None]:
    """
    Yield SSE events for each LangGraph node completion.
    Each event carries: { node: str, state: dict }
    On completion yields: data: [DONE]
    """
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}

    try:
        async for event in graph.astream_events(
            initial_state.to_serializable(),
            config=config,
            version="v2",
        ):
            event_type: str = event.get("event", "")
            name: str = event.get("name", "")

            if event_type == "on_chain_end" and name in {
                "ingest", "compress", "embed_and_cache",
                "generate", "critique", "resolve", "iterate",
            }:
                output_data: dict[str, Any] = event.get("data", {}).get("output", {})
                payload = json.dumps({"node": name, "state": output_data})
                yield f"data: {payload}\n\n"

    except Exception as exc:
        logger.error("Graph streaming error (thread=%s): %s", thread_id, exc)
        error_payload = json.dumps({"error": str(exc)})
        yield f"data: {error_payload}\n\n"
    finally:
        yield "data: [DONE]\n\n"


# ── Routes ────────────────────────────────────────────────────────────────────

@app.post("/generate")
async def generate(
    req: GenerateRequest,
    _: None = Depends(verify_pipeline_secret),
) -> StreamingResponse:
    """
    Start or resume a graph run.

    - First call: provide jd_raw (+ optional resume_raw). A new thread_id is allocated.
    - Subsequent calls (iteration): provide the same thread_id + user_iteration_feedback.
    - To approve and end the loop: set approved=True.
    """
    lf = Langfuse()
    trace = lf.trace(
        name="resume_generation",
        metadata={
            "has_resume": bool(req.resume_raw),
            "is_iteration": bool(req.thread_id),
        },
    )

    thread_id = req.thread_id or str(uuid.uuid4())

    initial_state = GraphState(
        jd_raw=req.jd_raw,
        resume_raw=req.resume_raw,
        user_iteration_feedback=req.user_iteration_feedback,
        approved=req.approved,
        langfuse_trace_id=trace.id,
    )

    async def _event_generator() -> AsyncGenerator[bytes, None]:
        async for chunk in _stream_graph_events(initial_state, thread_id):
            yield chunk.encode()

        # After graph completes, attempt to cache the result
        try:
            final_config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
            snapshot = graph.get_state(final_config)
            if snapshot and snapshot.values:
                final_state = GraphState(**snapshot.values)
                if final_state.resume_output and not final_state.cache_hit:
                    await store_cache(final_state)
        except Exception as exc:
            logger.warning("Cache storage failed after generation: %s", exc)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "X-Thread-ID": thread_id,
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/cache/status")
async def cache_status(
    jd_hash: str,
    _: None = Depends(verify_pipeline_secret),
) -> dict[str, Any]:
    """Check if a JD hash has a cached resume result."""
    from supabase import create_client

    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )
    result = (
        supabase.table("resume_cache")
        .select("id, hit_count, created_at")
        .eq("jd_hash", jd_hash)
        .maybe_single()
        .execute()
    )
    return {"cached": bool(result.data), "data": result.data}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
