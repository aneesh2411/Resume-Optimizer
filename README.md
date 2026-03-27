# Resume Optimizer

AI-powered resume tailoring system. Paste a job description and your LaTeX resume — the system produces a single-page, ATS-optimized PDF using a multi-agent pipeline with parallel persona critique, structured debate, and human-in-the-loop review.

## How It Works

1. **Ingest & validate** — sanitize and validate the job description and LaTeX input
2. **Semantic cache lookup** — if a similar JD was processed before (cosine ≥ 0.92), return the cached PDF instantly
3. **Analyze** — extract LaTeX structure (regex-only, no LLM)
4. **Generate** — produce tailored LaTeX via Claude Sonnet 4.6 + Instructor
5. **Critique (parallel)** — 5 AI personas score and flag the resume simultaneously
6. **Debate** — personas respond to each other, synthesize consensus with blocking vs. optional issues
7. **Human review (HITL)** — pipeline pauses; user can approve, regenerate, or edit LaTeX inline
8. **Compile** — Tectonic renders LaTeX → PDF
9. **Compress** — regex-based compression if output exceeds one page (max 2 attempts)
10. **Cache & store** — save to Supabase pgvector for future semantic lookups

The entire pipeline streams to the browser via Server-Sent Events (SSE).

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 15 + React 19 + TypeScript + Tailwind v4 |
| State | Zustand (persisted to localStorage) |
| PDF Preview | PDF.js viewer (A4) |
| Code Editor | Monaco Editor (inline LaTeX editing) |
| AI Pipeline | Python FastAPI + LangGraph |
| LLMs | Claude Sonnet 4.6 (primary), GPT-4o (fallback + embeddings) |
| Structured Output | Instructor + Pydantic |
| JD Compression | LLMLingua-2 |
| Semantic Cache | Supabase pgvector (HNSW, cosine ≥ 0.92) |
| Session Cache | Upstash Redis (1hr TTL) |
| LaTeX Compiler | Tectonic 0.15.0 (Rust-based, Docker) |
| Compile Queue | Azure Service Bus |
| PDF Storage | Azure Blob Storage (SAS URLs, 2hr expiry) |
| Observability | Langfuse |

## LangGraph Pipeline

```
[START] → ingest → embed_and_cache
  ├─ CACHE HIT → END (returns pdf_url from Supabase)
  └─ CACHE MISS → analyze_latex → generate → [Send() fan-out]
       ↓ (5 parallel persona critique workers)
       → debate → human_review [INTERRUPT]
         ├─ regen  → generate (loop)
         ├─ edit   → compile
         └─ approve → compile → compress_latex → cache_and_store → [END]
```

**Key patterns:**
- Nodes are pure functions: `GraphState` in → `dict` of changed keys out
- `Send()` fan-out for parallel persona critiques; merged via `Annotated[list, operator.add]`
- HITL via LangGraph `interrupt()` — graph pauses, frontend resumes with `Command(resume={...})`
- Thread ID stored in Upstash Redis for session restore across page reloads

## AI Personas

Five personas run in parallel during the critique phase:

| Persona | Focus |
|---------|-------|
| ATS Recruiter | Keyword density, formatting, ATS parse-ability |
| FAANG Bar Raiser | Impact metrics, scope, leadership signals |
| Principal Engineer | Technical depth, architecture, systems thinking |
| Startup CTO | Bias to action, ownership, full-stack breadth |
| AI/ML Researcher | ML rigor, publications, research methodology |

## Single-Page Enforcement (3 layers)

1. **Pydantic schema** — `word_count: int = Field(..., le=600)`; Instructor retries on violation
2. **`compress_latex` node** — regex compression loop; retries compile up to 2 times
3. **Frontend** — `DensityMeter` turns red; `ExportButton` disabled when `word_count > 600`

## Project Structure

```
├── app/                        # Next.js App Router
│   ├── page.tsx                # Landing: JD + resume input
│   ├── resume/
│   │   └── page.tsx            # Review: PDF viewer, critique, HITL
│   └── api/
│       ├── generate/           # SSE proxy → FastAPI pipeline
│       ├── export/             # PDF export endpoint
│       └── cache/              # Cache status endpoint
├── components/
│   ├── HITLPanel.tsx           # Human-in-the-loop approve/regen/edit UI
│   ├── DebatePanel.tsx         # Persona debate display
│   ├── CritiquePanel.tsx       # Tabbed persona critique view
│   ├── MonacoEditor.tsx        # Inline LaTeX editor
│   ├── PDFViewer.tsx           # PDF.js A4 preview
│   ├── DiffViewer.tsx          # Before/after LaTeX diff
│   ├── DensityMeter.tsx        # Word budget indicator
│   └── ExportButton.tsx        # PDF export (blocked on overflow)
├── store/
│   └── resumeStore.ts          # Zustand global state (threadId, history)
├── lib/
│   ├── supabase.ts             # Browser + server Supabase clients
│   ├── redis.ts                # Upstash session cache
│   └── langfuse.ts             # Observability client
├── pipeline/                   # Python FastAPI + LangGraph
│   ├── main.py                 # FastAPI app, SSE /generate, Service Bus consumer
│   ├── graph.py                # LangGraph graph topology and routing
│   ├── schemas.py              # Pydantic models + GraphState TypedDict
│   ├── compiler.py             # Tectonic LaTeX → PDF compilation
│   ├── storage.py              # Azure Blob Storage client
│   ├── nodes/                  # 13 individual graph node implementations
│   │   ├── ingest.py
│   │   ├── critique.py         # Parallel persona critique (Send() fan-out)
│   │   ├── debate.py           # Cross-persona debate synthesis
│   │   ├── human_review.py     # LangGraph interrupt (HITL)
│   │   ├── generate.py         # Claude/GPT-4o via Instructor
│   │   ├── compile.py          # Tectonic compile
│   │   ├── compress_latex.py   # Single-page enforcement
│   │   ├── resolve.py          # Conflict resolution
│   │   └── cache_and_store.py  # Supabase pgvector write
│   ├── personas/               # 5 persona markdown files
│   └── tests/                  # pytest test suite
└── supabase/
    └── migrations/
        ├── 001_pgvector.sql    # pgvector extension, resume_cache, sessions
        ├── 002_personas_table.sql
        └── 003_update_resume_cache.sql
```

## Quick Start

### Prerequisites

- Node.js 20+ and pnpm
- Python 3.12+ and uv
- Supabase project (free tier works)
- Upstash Redis (free tier works)
- Anthropic API key + OpenAI API key
- Azure Storage account + Service Bus namespace

### Setup

1. **Clone and install**
   ```bash
   pnpm install
   cd pipeline && uv sync
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env.local
   # Fill in all values — see Environment Variables section
   ```

3. **Run database migrations**
   ```bash
   supabase db push
   # Or paste migrations manually into the Supabase SQL editor
   ```

4. **Start the Python pipeline**
   ```bash
   cd pipeline
   uv run uvicorn main:app --reload --port 8000
   ```

5. **Start Next.js**
   ```bash
   pnpm dev
   ```

6. Open [http://localhost:3000](http://localhost:3000)

## Environment Variables

All variables are documented in `.env.example`. Key groups:

| Group | Variables |
|-------|-----------|
| Supabase | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` |
| LLMs | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` |
| Internal auth | `PIPELINE_URL`, `PIPELINE_SECRET` |
| Upstash Redis | `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN` |
| Azure Service Bus | `SERVICEBUS_CONN`, `SERVICEBUS_QUEUE` |
| Azure Storage | `AZURE_STORAGE_CONN`, `AZURE_STORAGE_ACCOUNT`, `AZURE_STORAGE_KEY` |
| Observability | `LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_HOST` |

## Commands

### Frontend

```bash
pnpm dev          # Dev server with Turbopack (port 3000)
pnpm build        # Production build
pnpm lint         # ESLint
pnpm type-check   # tsc --noEmit
pnpm test         # Vitest
pnpm test:watch   # Vitest watch mode
```

### Python Pipeline

```bash
cd pipeline
uv sync                                          # Install deps
uv run uvicorn main:app --reload --port 8000    # Dev server
uv run pytest                                    # All tests
uv run pytest tests/test_critique.py            # Single test file
uv run ruff check .                              # Lint
uv run mypy .                                    # Type check (strict)
```

## Deployment

- **Frontend**: Deploy to Vercel — set all `NEXT_PUBLIC_*` and server-side env vars
- **Pipeline**: Deploy as a Docker container (Railway, Fly.io, Azure Container Apps) — Tectonic is bundled in `pipeline/Dockerfile`
- **Database**: Run migrations via `supabase db push` against your hosted project
