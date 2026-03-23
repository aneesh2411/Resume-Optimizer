# Resume Optimizer

AI-powered resume tailoring application. Paste a job description, receive a single-page ATS-optimized resume with multi-persona critique from a recruiter, hiring manager, and industry expert.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15 + React 19 + TypeScript + Tailwind v4 |
| State | Zustand |
| PDF Preview | @react-pdf/renderer (A4 locked) |
| PDF Export | Puppeteer + @sparticuz/chromium |
| AI Pipeline | Python FastAPI + LangGraph |
| LLMs | Claude claude-sonnet-4-6 (primary), GPT-4o (fallback) |
| Structured Output | Instructor + Pydantic |
| JD Compression | LLMLingua-2 |
| Validation | Guardrails AI |
| Semantic Cache | Supabase pgvector (HNSW, cosine ≥ 0.92) |
| Session Cache | Upstash Redis |
| Observability | Langfuse |

## Quick Start

### Prerequisites
- Node.js 20+ and pnpm
- Python 3.12+ and uv
- Supabase project (free tier works)
- Upstash Redis (free tier works)
- Anthropic API key + OpenAI API key

### Setup

1. **Clone and install**
   ```bash
   pnpm install
   cd pipeline && uv sync
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env.local
   # Fill in all values in .env.local
   ```

3. **Database**
   ```bash
   # With Supabase CLI:
   supabase db push
   # Or paste supabase/migrations/001_pgvector.sql into the Supabase SQL editor
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

## Project Structure

```
├── app/                    # Next.js App Router
│   ├── page.tsx            # Landing: JD + resume input
│   ├── resume/
│   │   ├── page.tsx        # Editor: A4 preview + critique + iteration
│   │   └── [id]/critique/  # Deep-link critique view
│   └── api/
│       ├── generate/       # SSE proxy → FastAPI
│       ├── export/         # Puppeteer PDF generation
│       └── cache/          # Cache status endpoint
├── components/
│   ├── ResumePreview.tsx   # react-pdf A4 viewport
│   ├── CritiquePanel.tsx   # Tabbed recruiter/HM/expert view
│   ├── IterationInput.tsx  # User feedback + regen
│   ├── DensityMeter.tsx    # Word budget indicator
│   └── ExportButton.tsx    # PDF export (blocked on overflow)
├── store/
│   └── resumeStore.ts      # Zustand global state
├── lib/
│   ├── supabase.ts         # Supabase clients
│   ├── redis.ts            # Upstash session cache
│   └── langfuse.ts         # Observability
├── pipeline/               # Python FastAPI + LangGraph
│   ├── main.py             # FastAPI app + SSE streaming
│   ├── graph.py            # LangGraph state machine
│   ├── schemas.py          # Pydantic data contracts
│   ├── nodes/              # Individual graph nodes
│   │   ├── ingest.py
│   │   ├── compress.py     # LLMLingua-2
│   │   ├── cache.py        # pgvector semantic cache
│   │   ├── generate.py     # Claude claude-sonnet-4-6 / GPT-4o via Instructor
│   │   ├── critique.py     # Parallel 3-persona critique
│   │   ├── resolve.py      # Conflict synthesis
│   │   └── iterate.py      # HITL loop
│   ├── personas/           # Persona markdown files
│   └── tests/              # pytest test suite
└── supabase/
    └── migrations/
        └── 001_pgvector.sql
```

## LangGraph Pipeline

```
[START]
  │
[ingest]          sanitise + truncate JD
  │
[compress]        LLMLingua-2 (50% token reduction)
  │
[embed_and_cache] SHA-256 exact match → pgvector semantic search
  │               cache hit → skip to resolve
  │
[generate]        Claude claude-sonnet-4-6 via Instructor → ResumeOutput
  │
[critique]        asyncio.gather (parallel):
  │               recruiter + hiring_manager + expert
  │
[resolve]         synthesise → ConflictResolution
  │
  ┤ ← INTERRUPT (HITL: user reviews critique, submits feedback or approves)
  │
[iterate]         clear outputs, re-enter generate with feedback
  │
[END]
```

## Single-Page Enforcement

Three layers enforce the 600-word single-page budget:

1. **Pydantic**: `word_count: int = Field(..., le=600)` — Instructor retries if violated
2. **compress_node**: validates word count after generation, triggers re-compress if needed
3. **Frontend**: `DensityMeter` shows red bar + `ExportButton` is disabled when `word_count > 600`

## Running Tests

```bash
# Python
cd pipeline && uv run pytest

# TypeScript
pnpm test
```

## Deployment

- **Frontend**: Deploy to Vercel (connects to GitHub automatically)
- **Pipeline**: Deploy FastAPI to Railway, Fly.io, or any container platform
- Set all environment variables in both deployment environments
