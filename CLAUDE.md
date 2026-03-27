# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

Resume Optimizer is an AI-powered resume tailoring system. Users paste a job description and LaTeX resume; the system produces a single-page, ATS-optimized PDF resume using a multi-agent AI pipeline with persona critique, debate, and human-in-the-loop review.

## Commands

### Frontend (Next.js)
```bash
pnpm dev          # Dev server with Turbopack on port 3000
pnpm build        # Production build
pnpm lint         # ESLint
pnpm type-check   # tsc --noEmit
pnpm test         # Vitest
pnpm test:watch   # Vitest watch mode
```

### Python Pipeline (FastAPI)
```bash
cd pipeline
uv sync                                         # Install deps
uv run uvicorn main:app --reload --port 8000   # Dev server
uv run pytest                                   # All tests
uv run pytest tests/test_critique.py           # Single test file
uv run ruff check .                             # Lint
uv run mypy .                                   # Type check (strict)
```

### Database
```bash
supabase db push   # Push migrations via Supabase CLI
```

## Architecture

### System Layers

1. **Frontend** (`app/`, `components/`, `store/`) — Next.js 15 + React 19 + TypeScript + Tailwind v4 + Zustand
2. **BFF** (`app/api/`) — Next.js API routes proxy to FastAPI; handle Redis session caching
3. **AI Pipeline** (`pipeline/`) — Python FastAPI + LangGraph state machine

### LangGraph Node Sequence

```
[START] → ingest → embed_and_cache
  ├─ CACHE HIT → END (returns pdf_url from Supabase pgvector)
  └─ CACHE MISS → analyze_latex → generate → [Send() fan-out]
       ↓ (5 parallel persona critique workers)
       → debate → human_review [INTERRUPT]
         ├─ regen → generate (loop)
         ├─ edit  → compile
         └─ approve → compile → compress_latex (if >1 page) → cache_and_store → [END]
```

**Critical patterns:**
- Nodes are pure functions: accept `GraphState`, return `dict` of changed keys only
- `Send()` fan-out for parallel persona critiques; merged via `Annotated[list, operator.add]`
- HITL via LangGraph `interrupt()` — graph pauses, frontend resumes with `Command(resume={...})`
- Semantic cache uses pgvector cosine similarity (0.92 threshold) on JD embeddings

### Data Flow: SSE Streaming

```
Browser → POST /api/generate → Next.js BFF → POST /pipeline/generate (FastAPI)
                                           ← SSE stream (node progress events)
                                           ← X-Thread-ID header (LangGraph checkpoint)
```

The BFF stores the thread ID in Upstash Redis (1hr TTL) for session restore.

### Key Files

| File | Purpose |
|------|---------|
| `pipeline/main.py` | FastAPI app, SSE `/generate` endpoint, Azure Service Bus consumer |
| `pipeline/graph.py` | LangGraph graph topology and routing logic |
| `pipeline/schemas.py` | Pydantic models + `GraphState` TypedDict |
| `pipeline/compiler.py` | Tectonic LaTeX → PDF compilation |
| `pipeline/nodes/` | 13 individual node implementations |
| `store/resumeStore.ts` | Zustand global state (threadId, history persisted to localStorage) |
| `next.config.ts` | Rewrites `/pipeline/*` → `${PIPELINE_URL}/*` |
| `lib/supabase.ts` | Browser + server Supabase clients |

### External Services

| Service | Purpose |
|---------|---------|
| Supabase PostgreSQL + pgvector | Resume cache (HNSW index, cosine similarity), sessions, personas |
| Upstash Redis | Session cache (BFF layer, 1hr TTL) |
| Azure Service Bus | Async LaTeX compile job queue |
| Azure Blob Storage | PDF storage + SAS URL generation (2hr expiry) |
| Langfuse | LLM observability and trace recording |
| Tectonic 0.15.0 | Rust-based LaTeX compiler (in Docker, no TeX Live) |

### AI Models

- **Claude Sonnet 4.6** — Primary: generation, critique, debate, consensus
- **GPT-4o** — Fallback; also used for JD embeddings (`text-embedding-3-small`, 1536 dims)
- **Instructor** — Structured output with Pydantic validation + auto-retry
- **LLMLingua-2** — JD compression before embedding/caching

### Single-Page Enforcement (3 layers)

1. **Pydantic schema** — `word_count: int = Field(..., le=600)`; Instructor retries on violation
2. **compress_latex node** — Regex-based compression; loops back to compile if still >1 page (max 2 attempts)
3. **Frontend** — `DensityMeter` shows red; `ExportButton` disabled when `word_count > 600`

### Personas

Five markdown files in `pipeline/personas/` loaded at runtime: `ats_recruiter`, `faang_bar_raiser`, `principal_engineer`, `startup_cto`, `ai_ml_researcher`.

## Database Schema

Three migrations in `supabase/migrations/`:
1. `001_pgvector.sql` — pgvector extension, `resume_cache` (jd_hash, jd_embedding, pdf_url, latex_output, hit_count), `resume_sessions`
2. `002_personas_table.sql` — `personas` table
3. `003_update_resume_cache.sql` — Adds `user_id`, `pdf_url`, `latex_output` columns

## Environment Variables

All required vars are in `.env.example`. Key ones:
- `PIPELINE_URL` / `PIPELINE_SECRET` — Internal Next.js ↔ FastAPI auth
- `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` — LLM APIs
- `NEXT_PUBLIC_SUPABASE_URL` + `NEXT_PUBLIC_SUPABASE_ANON_KEY` — Client-side Supabase
- `SUPABASE_SERVICE_ROLE_KEY` — Server-side Supabase (BFF + pipeline)
- `UPSTASH_REDIS_REST_URL` + `UPSTASH_REDIS_REST_TOKEN` — Session cache
- `SERVICEBUS_CONN` + `SERVICEBUS_QUEUE` — Azure compile queue
- `AZURE_STORAGE_CONN` / `AZURE_STORAGE_ACCOUNT` / `AZURE_STORAGE_KEY` — PDF storage
- `LANGFUSE_SECRET_KEY` + `LANGFUSE_PUBLIC_KEY` — Observability
