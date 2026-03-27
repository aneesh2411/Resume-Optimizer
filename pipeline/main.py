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

import asyncio
import hashlib
import hmac
import json
import logging
import os
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from azure.servicebus.aio import ServiceBusClient
from dotenv import load_dotenv
from upstash_redis.asyncio import Redis as AsyncRedis
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langfuse import Langfuse
from pydantic import BaseModel

load_dotenv()                              # load .env
load_dotenv(".env.local", override=True)  # override with .env.local if present

from pipeline.graph import graph  # noqa: E402 (must be after load_dotenv)
from pipeline.schemas import GraphState  # noqa: E402
from pipeline.compiler import compile_latex  # noqa: E402
from pipeline.models import CompileJob, CompileResult  # noqa: E402
from pipeline.storage import upload_pdf  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)


# ── LaTeX Service Bus consumer ────────────────────────────────────────────────

async def _process_compile_jobs() -> None:
    """Background task: consume LaTeX compile jobs from Azure Service Bus."""
    redis = AsyncRedis(
        url=os.environ["UPSTASH_REDIS_REST_URL"],
        token=os.environ["UPSTASH_REDIS_REST_TOKEN"],
    )
    async with ServiceBusClient.from_connection_string(
        os.environ["SERVICEBUS_CONN"]
    ) as client:
        logger.info("Listening for compile jobs on queue '%s'...", os.environ["SERVICEBUS_QUEUE"])
        while True:
            async with client.get_queue_receiver(
                queue_name=os.environ["SERVICEBUS_QUEUE"],
                max_wait_time=5,
            ) as receiver:
                async for msg in receiver:
                    try:
                        data = json.loads(msg.body)
                        job = CompileJob(**data)
                        logger.info("Processing compile job %s for user %s", job.job_id, job.user_id)

                        success, pdf_bytes, error, page_count = compile_latex(job)

                        if success:
                            pdf_url = upload_pdf(job.job_id, pdf_bytes)
                            result = CompileResult(
                                job_id=job.job_id,
                                success=True,
                                pdf_url=pdf_url,
                                page_count=page_count,
                            )
                            logger.info("Compile job %s complete: %s", job.job_id, pdf_url)
                        else:
                            result = CompileResult(
                                job_id=job.job_id,
                                success=False,
                                error=error,
                                page_count=0,
                            )
                            logger.error("Compile job %s failed: %s", job.job_id, error[:200])

                        await redis.setex(
                            f"compile_result:{job.job_id}",
                            3600,
                            result.model_dump_json(),
                        )
                        await receiver.complete_message(msg)

                    except Exception as exc:
                        logger.error(
                            "Fatal error processing compile job (body=%r): %s",
                            str(msg.body)[:200],
                            exc,
                            exc_info=True,
                        )
                        await receiver.dead_letter_message(msg, reason=str(exc)[:4096])


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = None
    if os.getenv("COMPILE_WORKER_ENABLED", "").lower() == "true":
        task = asyncio.create_task(_process_compile_jobs())
    yield
    if task:
        task.cancel()


app = FastAPI(title="Resume Pipeline", version="0.1.0", docs_url="/docs", lifespan=lifespan)

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
    latex_input: str
    selected_persona_ids: list[str]
    thread_id: str | None = None
    # HITL resume fields — set when the frontend POSTs Command(resume={...})
    human_decision: str | None = None   # "approve" | "edit" | "regen"
    edited_latex: str | None = None


class PersonaGenerateRequest(BaseModel):
    description: str   # plain-English description of the desired persona


# ── SSE streaming ─────────────────────────────────────────────────────────────

_STREAM_NODES = {
    "ingest_node", "embed_and_cache_node", "analyze_latex_node",
    "generate_node", "critique_persona", "debate_node",
    "human_review_node", "compile_node", "compress_latex_node",
    "cache_and_store_node",
}


async def _stream_graph_events(
    input_or_command: Any,
    thread_id: str,
) -> AsyncGenerator[str, None]:
    """
    Yield SSE events for each LangGraph node completion.
    Each event carries: { node: str, state: dict }
    On completion yields: data: [DONE]

    input_or_command may be a plain GraphState dict (new run) or a
    langgraph.types.Command object (HITL resume).
    """
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}

    try:
        async for event in graph.astream_events(
            input_or_command,
            config=config,
            version="v2",
        ):
            event_type: str = event.get("event", "")
            name: str = event.get("name", "")

            if event_type == "on_chain_end" and name in _STREAM_NODES:
                output_data: dict[str, Any] = event.get("data", {}).get("output", {})
                payload = json.dumps(
                    {"node": name, "state": output_data},
                    default=lambda o: o.model_dump() if hasattr(o, "model_dump") else repr(o),
                )
                yield f"data: {payload}\n\n"

            # Detect LangGraph interrupt() — emitted as on_chain_stream with __interrupt__ key
            elif event_type == "on_chain_stream" and name == "LangGraph":
                chunk = event.get("data", {}).get("chunk", {})
                if "__interrupt__" in chunk:
                    interrupts = chunk["__interrupt__"]
                    if interrupts:
                        interrupt_value = interrupts[0].value if hasattr(interrupts[0], "value") else interrupts[0]
                        payload = json.dumps(
                            {"node": "human_review_node", "state": {"hitl": interrupt_value}},
                            default=lambda o: o.model_dump() if hasattr(o, "model_dump") else repr(o),
                        )
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

    New run:   provide jd_raw + latex_input + selected_persona_ids.
               A new thread_id is minted and returned in X-Thread-ID header.
    HITL resume: provide the same thread_id + human_decision (+ edited_latex if "edit").
                 The graph resumes from the interrupt() checkpoint.
    """
    from langgraph.types import Command  # local import avoids circular at module level

    lf = Langfuse()
    trace = lf.start_observation(
        name="resume_generation",
        metadata={
            "is_resume": bool(req.human_decision),
            "thread_id": req.thread_id,
        },
    )

    thread_id = req.thread_id or str(uuid.uuid4())

    if req.human_decision:
        # HITL resume — graph was paused at human_review_node via interrupt()
        input_or_command = Command(
            resume={
                "decision": req.human_decision,
                "edited_latex": req.edited_latex,
            }
        )
    else:
        # New run
        input_or_command = {
            "jd_raw": req.jd_raw,
            "latex_input": req.latex_input,
            "selected_persona_ids": req.selected_persona_ids,
            "cache_hit": False,
            "compression_attempts": 0,
            "overflow_error": False,
            "critique_results": [],
            "langfuse_trace_id": trace.trace_id,
        }

    async def _event_generator() -> AsyncGenerator[bytes, None]:
        async for chunk in _stream_graph_events(input_or_command, thread_id):
            yield chunk.encode()

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
    data = result.data if result is not None else None
    return {"cached": bool(data), "data": data}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/personas/generate")
async def personas_generate(
    req: PersonaGenerateRequest,
    request: Request,
    _: None = Depends(verify_pipeline_secret),
) -> dict[str, Any]:
    """
    Generate a new persona markdown from a plain-English description.

    The caller (Next.js route handler) must set X-User-ID to the authenticated user's UUID.
    The generated persona is inserted into the Supabase personas table.
    """
    import re
    import anthropic as _anthropic
    from supabase import create_client

    user_id: str | None = request.headers.get("X-User-ID")

    client = _anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    system_prompt = (
        "You are a resume evaluation expert who creates brutally honest, highly specific "
        "technical hiring personas. Generate a persona markdown file following this exact format:\n\n"
        "# [Persona Name]\n\n"
        "## Background\n"
        "[3 sentences about role, years of experience, specific companies/context]\n\n"
        "## Focus Areas\n"
        "- [5 specific evaluation bullets]\n\n"
        "## Scoring Rubric\n"
        "- [Issue description]: -[N] pts\n"
        "...(5-7 rubric items)\n\n"
        "## Signature Flag\n"
        '> "[One damning quote they always say when reviewing a weak resume]"\n\n'
        "Be specific, brutal, and opinionated. Avoid generic platitudes."
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": f"Create a hiring persona for: {req.description}"}],
        system=system_prompt,
    )
    markdown = message.content[0].text.strip()

    # Extract persona name from first heading
    name_match = re.match(r"#\s+(.+)", markdown)
    name = name_match.group(1).strip() if name_match else req.description[:50]

    # Derive a slug persona_id from the name
    persona_id = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")

    row: dict[str, Any] = {
        "name": name,
        "persona_id": persona_id,
        "markdown": markdown,
        "user_id": user_id,
        "is_public": False,
    }

    try:
        supabase = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        )
        result = supabase.table("personas").upsert(
            row,
            on_conflict="user_id,persona_id",
        ).execute()
        saved = result.data[0] if result.data else row
    except Exception as exc:
        logger.error("personas_generate: Supabase insert failed: %s", exc)
        saved = row

    return saved


@app.post("/compile-direct")
async def compile_direct(job: CompileJob) -> CompileResult:
    """Direct HTTP endpoint for testing LaTeX compilation without Service Bus."""
    logger.info("Direct compile request for job %s (user %s)", job.job_id, job.user_id)
    success, pdf_bytes, error, page_count = compile_latex(job)
    if success:
        pdf_url = upload_pdf(job.job_id, pdf_bytes)
        logger.info("Direct compile job %s complete: %s", job.job_id, pdf_url)
        return CompileResult(job_id=job.job_id, success=True, pdf_url=pdf_url, page_count=page_count)
    logger.error("Direct compile job %s failed: %s", job.job_id, error[:200])
    return CompileResult(job_id=job.job_id, success=False, error=error)
