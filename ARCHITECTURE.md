# Resume Optimizer — Full Architecture & System Understanding

> Last updated: 2026-03-25
> Stack: Next.js 15 · FastAPI · LangGraph · Supabase · Azure · Upstash Redis · Langfuse

---

## Table of Contents

1. [What This Project Does](#1-what-this-project-does)
2. [High-Level System Map](#2-high-level-system-map)
3. [Repository Structure](#3-repository-structure)
4. [Frontend — Next.js App](#4-frontend--nextjs-app)
   - [Pages](#pages)
   - [API Routes (BFF Layer)](#api-routes-bff-layer)
   - [Components](#components)
   - [State Management (Zustand)](#state-management-zustand)
   - [Utility Libraries](#utility-libraries)
5. [Backend — Python FastAPI Pipeline](#5-backend--python-fastapi-pipeline)
   - [FastAPI Server (main.py)](#fastapi-server-mainpy)
   - [LangGraph Node Topology (graph.py)](#langgraph-node-topology-graphpy)
   - [Node-by-Node Breakdown](#node-by-node-breakdown)
   - [Personas](#personas)
6. [Database — Supabase (PostgreSQL + pgvector)](#6-database--supabase-postgresql--pgvector)
7. [Infrastructure & Deployment](#7-infrastructure--deployment)
   - [Azure Container App (latex-compiler)](#azure-container-app-latex-compiler)
   - [Azure Service Bus](#azure-service-bus)
   - [Azure Blob Storage](#azure-blob-storage)
   - [Upstash Redis](#upstash-redis)
   - [Langfuse Observability](#langfuse-observability)
8. [Full Data Flow — Request Lifecycle](#8-full-data-flow--request-lifecycle)
   - [Phase 1: New Generation (Cache Miss)](#phase-1-new-generation-cache-miss)
   - [Phase 2: HITL Decision](#phase-2-hitl-decision)
   - [Phase 3: Compile → Store → Done](#phase-3-compile--store--done)
   - [Cache Hit Path (Fast Path)](#cache-hit-path-fast-path)
9. [Environment Variables](#9-environment-variables)
10. [Service Linkage Map](#10-service-linkage-map)
11. [How to Run Everything Locally](#11-how-to-run-everything-locally)
12. [Testing Overview](#12-testing-overview)
13. [Known Gaps & TODOs](#13-known-gaps--todos)

---

## 1. What This Project Does

Resume Optimizer takes a job description (JD) and a LaTeX resume, and runs them through a multi-agent AI pipeline to produce a tailored, ATS-optimized, single-page PDF resume. The key stages:

1. **Ingest & validate** the JD and LaTeX
2. **Semantic cache lookup** — if a very similar JD was processed before, return the cached PDF immediately
3. **Analyze** the existing LaTeX structure (regex-only, no LLM)
4. **Generate** a tailored LaTeX resume using Claude Sonnet 4.6
5. **Critique in parallel** — 1–5 AI personas (ATS Recruiter, FAANG Bar Raiser, Principal Engineer, Startup CTO, AI/ML Researcher) each score and flag the resume simultaneously
6. **Debate** — personas respond to each other's flags and synthesise a consensus with blocking issues vs. optional improvements
7. **Human-in-the-loop (HITL)** — graph pauses and shows the user the resume + critique; user can approve, regenerate, or edit the LaTeX
8. **Compile** the LaTeX to PDF using Tectonic
9. **Compress** if the output is more than one page (regex-based, up to 2 attempts)
10. **Cache & store** the result in Supabase for future semantic lookups

The entire pipeline is streamed to the browser via Server-Sent Events (SSE).

---

## 2. High-Level System Map

```
┌────────────────────────────────────────────────────────────────────────────┐
│                          User's Browser                                     │
│                                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌───────────────────────────────┐ │
│  │  page.tsx    │    │ resume/page  │    │  /resume/[id]/critique/page   │ │
│  │  (Landing)   │    │ (Review)     │    │  (Deep-link critique view)    │ │
│  └──────┬───────┘    └──────┬───────┘    └───────────────────────────────┘ │
│         │                   │                                               │
│         └──────────── Zustand Store (resumeStore.ts) ─────────────────────┘│
│                   (localStorage: threadId, history, jd)                     │
└────────────────────────────────────┬───────────────────────────────────────┘
                                     │ SSE stream (text/event-stream)
                                     │ POST /api/generate
                                     ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                      Next.js API Routes (BFF)                               │
│                                                                             │
│  /api/generate          → Proxy to FastAPI, cache threadId in Redis        │
│  /api/cache             → Check Supabase resume_cache by jd_hash           │
│  /api/personas/generate → Proxy to FastAPI, resolve Supabase user          │
└──────┬────────────────────────────────────────────┬─────────────────────────┘
       │                                            │
       │ POST /generate (SSE)                       │ GET/POST (sync)
       ▼                                            ▼
┌─────────────────────────────────┐    ┌──────────────────┐  ┌───────────────┐
│   FastAPI Pipeline              │    │  Upstash Redis   │  │   Supabase    │
│   (Python 3.12, uvicorn)        │    │  (session cache) │  │  (resume DB)  │
│                                 │    └──────────────────┘  └───────────────┘
│   LangGraph State Machine       │
│   ┌─────────────────────────┐   │    ┌──────────────────────────────────────┐
│   │ ingest_node             │   │    │  Azure Container App                  │
│   │ embed_and_cache_node    │   │    │  latex-compiler                       │
│   │ analyze_latex_node      │   │    │  (FastAPI + Tectonic + pypdf)         │
│   │ generate_node           │   │    │                                       │
│   │ critique_persona × N ──────────→ POST /compile-direct                   │
│   │ debate_node             │   │    │  ↓ Compile LaTeX → PDF bytes          │
│   │ human_review_node       │   │    │  ↓ Upload to Azure Blob               │
│   │ compile_node            │   │    │  ↓ Return pdf_url + page_count        │
│   │ compress_latex_node     │   │    └──────────────────────────────────────┘
│   │ cache_and_store_node    │   │
│   └─────────────────────────┘   │    ┌──────────────────────────────────────┐
│                                 │    │  Azure Blob Storage                   │
│   External calls:               │    │  resumeoptimizerstor / pdfs           │
│   • Anthropic Claude Sonnet 4.6 │    │  resumes/{job_id}.pdf (SAS, 2hr)     │
│   • OpenAI text-embedding-3-sm  │    └──────────────────────────────────────┘
│   • Supabase pgvector cache     │
│   • Langfuse (tracing)          │    ┌──────────────────────────────────────┐
└─────────────────────────────────┘    │  Langfuse (cloud.langfuse.com)        │
                                       │  Traces all LLM calls, node spans     │
                                       └──────────────────────────────────────┘
```

---

## 3. Repository Structure

```
Resume-Optimizer/
│
├── app/                          # Next.js App Router pages + API routes
│   ├── page.tsx                  # Landing: JD input, LaTeX editor, start generation
│   ├── layout.tsx                # Root HTML layout + metadata
│   ├── globals.css               # Tailwind global styles
│   ├── resume/
│   │   ├── page.tsx              # Resume review page (PDF, diff, critique, HITL)
│   │   └── [id]/critique/
│   │       └── page.tsx          # Deep-link critique view by thread ID
│   └── api/
│       ├── generate/route.ts     # SSE proxy to FastAPI + Redis session caching
│       ├── cache/route.ts        # Supabase jd_hash cache lookup
│       └── personas/generate/
│           └── route.ts          # Persona generation proxy with Supabase auth
│
├── components/
│   ├── CritiquePanel.tsx         # Tabbed per-persona critique display
│   ├── DebatePanel.tsx           # Debate rounds accordion + consensus
│   ├── DensityMeter.tsx          # Word budget bar + ATS score + format badge
│   ├── DiffViewer.tsx            # Line-by-line LaTeX diff visualization
│   ├── ExportButton.tsx          # PDF download link from Azure Blob URL
│   ├── HITLPanel.tsx             # Approve / Regen / Edit LaTeX decision UI
│   ├── MonacoEditor.tsx          # Monaco editor wrapper (read-only or editable)
│   └── PDFViewer.tsx             # PDF.js canvas renderer for compiled PDF
│
├── lib/
│   ├── langfuse.ts               # Langfuse singleton client (tracing)
│   ├── redis.ts                  # Upstash Redis client + session helpers
│   ├── supabase.ts               # Supabase browser + server client factories
│   └── utils.ts                  # cn() class merge utility
│
├── store/
│   └── resumeStore.ts            # Zustand global store (all pipeline state)
│
├── supabase/
│   └── migrations/
│       ├── 001_pgvector.sql      # Extension + resume_cache + resume_sessions tables
│       ├── 002_personas_table.sql # personas table
│       └── 003_update_resume_cache.sql # Add user_id, pdf_url, latex_output columns
│
├── pipeline/                     # Python FastAPI + LangGraph backend
│   ├── main.py                   # FastAPI server, SSE endpoint, Service Bus consumer
│   ├── graph.py                  # LangGraph topology (all nodes + edges)
│   ├── models.py                 # Compile job/result Pydantic models
│   ├── schemas.py                # GraphState + all shared Pydantic models
│   ├── compiler.py               # Tectonic LaTeX → PDF + pypdf page count
│   ├── storage.py                # Azure Blob upload + SAS URL generation
│   ├── nodes/
│   │   ├── ingest.py             # Input validation + sanitization
│   │   ├── cache.py              # LLMLingua compression + hash + pgvector lookup
│   │   ├── analyze_latex.py      # Regex-based LaTeX structural analysis
│   │   ├── generate.py           # Claude resume generation (Instructor)
│   │   ├── critique.py           # Send() fan-out per persona + ai-slop detection
│   │   ├── debate.py             # Parallel debate rounds + consensus synthesis
│   │   ├── human_review.py       # interrupt() HITL node + routing
│   │   ├── compile.py            # HTTP POST to /compile-direct + routing
│   │   ├── compress_latex.py     # Regex LaTeX compression loop
│   │   ├── cache_and_store.py    # Upsert final resume into Supabase
│   │   ├── iterate.py            # (unused) legacy regen helper
│   │   └── resolve.py            # (unused) legacy conflict resolver
│   ├── personas/
│   │   ├── ats_recruiter.md
│   │   ├── faang_bar_raiser.md
│   │   ├── principal_engineer.md
│   │   ├── startup_cto.md
│   │   └── ai_ml_researcher.md
│   ├── tests/                    # pytest test suites
│   ├── Dockerfile                # python:3.12-slim + Tectonic 0.15.0
│   ├── pyproject.toml            # Python deps + ruff + mypy config
│   └── requirements.txt          # Pinned runtime deps (for Docker)
│
├── next.config.ts                # Next.js config + /pipeline/* rewrites
├── package.json                  # NPM deps + scripts
├── tsconfig.json                 # TypeScript strict config
├── vitest.config.ts              # Vitest (jsdom, @vitejs/plugin-react)
└── .env.example                  # All required env vars documented
```

---

## 4. Frontend — Next.js App

### Pages

#### `app/page.tsx` — Landing Page
The entry point. Users paste a job description, their LaTeX resume (in Monaco editor), and select which AI personas to use. On submit:
- POSTs to `/api/generate` and opens an SSE stream
- Parses `data: {...}` events in real-time and writes to Zustand store
- Each event carries `{ node, state }` identifying which pipeline step just finished
- On `human_review_node` event → stores `hitlPayload` and navigates to `/resume`
- On `[DONE]` → sets `isStreaming = false`

**Node events tracked:** `ingest_node`, `embed_and_cache_node`, `analyze_latex_node`, `generate_node`, `critique_persona`, `debate_node`, `human_review_node`, `compile_node`, `compress_latex_node`, `cache_and_store_node`

#### `app/resume/page.tsx` — Resume Review Page
Two-column layout shown after the pipeline emits a HITL interrupt:
- **Left:** DensityMeter + PDFViewer (if compiled) or DiffViewer (pre-compile) + ExportButton
- **Right:** DebatePanel + HITLPanel (when interrupted) + iteration history

#### `app/resume/[id]/critique/page.tsx` — Deep-link Critique
Validates `params.id === threadId` from Zustand. Shows CritiquePanel + ExportButton for a specific session.

---

### API Routes (BFF Layer)

#### `POST /api/generate` → SSE Proxy
- Forwards request body to `${PIPELINE_URL}/generate` with `X-Pipeline-Secret` auth header
- Extracts `X-Thread-ID` from pipeline response
- Stores `{ startedAt, body }` in Upstash Redis under key `session:{threadId}` (1hr TTL)
- Streams the pipeline's SSE response verbatim to the browser
- Runtime: Node.js (not Edge) — needed for 120s timeout + streaming

#### `GET /api/cache` → Cache Check
- Accepts `?jd_hash=<sha256>`
- Queries Supabase `resume_cache` table (server client, service role)
- Returns `{ cached: true/false, data: { id, hit_count, created_at } }`

#### `POST /api/personas/generate` → Persona Generation Proxy
- Resolves Supabase user from `Authorization: Bearer <token>` header
- Forwards body to `${PIPELINE_URL}/personas/generate` with `X-User-ID` header
- Returns pipeline response verbatim

---

### Components

| Component | Purpose | External Data |
|-----------|---------|---------------|
| `CritiquePanel` | Tabbed per-persona score, flags, suggestions, AI slop badge | Zustand `critique`, `consensus` |
| `DebatePanel` | Debate round accordions + consensus blocking/optional issues | Zustand `critique`, `consensus` |
| `DensityMeter` | Word count progress bar (600-word budget), ATS score, format badge (STAR/XYZ/CAR) | Zustand `latexOutput` |
| `DiffViewer` | Unified diff of original vs. generated LaTeX using `diff` npm package | Props: `original`, `modified` |
| `ExportButton` | `<a download>` link pointing to Azure Blob SAS URL | Zustand `pdfUrl`, `threadId` |
| `HITLPanel` | Approve / Regen / Edit LaTeX decision UI; re-opens SSE stream on decision | POST `/api/generate`, Zustand |
| `MonacoEditor` | Monaco wrapper for LaTeX editing (read-only or editable) | Controlled via props |
| `PDFViewer` | Renders PDF page 1 on HTML canvas via pdfjs-dist | Prop: `url` (Azure Blob SAS URL) |

---

### State Management (Zustand)

**File:** `store/resumeStore.ts`
**Persistence:** `localStorage` (key: `resume-optimizer-store`)

**What is persisted to localStorage:**
- `threadId` — LangGraph checkpoint thread
- `history` — array of past `LaTeXOutput` versions (for iteration tracking)
- `jd` — job description text

**What is NOT persisted (cleared on page reload):**
- `latexOutput`, `pdfUrl`, `critique`, `consensus`, `hitlPayload`, `isStreaming`, `currentNode`, `error`

**Key state domains:**

```
Session:   threadId, jd, latexInput, personaIds
Pipeline:  isStreaming, currentNode, error
Outputs:   latexOutput, pdfUrl, critique, consensus, hitlPayload, history
```

**Key actions:**
- `setLatexOutput()` — auto-archives previous output to `history`
- `reset()` — clears pipeline state but preserves `jd`, `latexInput`, `personaIds`

**TypeScript types mirroring Pydantic schemas:**
- `LaTeXOutput` — full LaTeX doc + sections + format_used + ats_score_estimate + word_count
- `CritiqueResult` — persona_id, score, flags[], suggestions[], ai_slop_detected, jd_match_confidence
- `DebateRound` — responding persona, agreements, disagreements, synthesis
- `DebateConsensus` — blocking_issues[], optional_improvements[], consensus_score, debate_rounds[]
- `HITLPayload` — latex, consensus, critique_results

---

### Utility Libraries

| File | Purpose |
|------|---------|
| `lib/supabase.ts` | Two Supabase clients: browser (anon key, RLS enforced) and server (service role, RLS bypassed) |
| `lib/redis.ts` | Upstash Redis client + `getSessionCache()` / `setSessionCache()` / `deleteSessionCache()` helpers. Key: `session:{threadId}`, TTL 1hr |
| `lib/langfuse.ts` | Singleton Langfuse tracing client for API routes |
| `lib/utils.ts` | `cn()` — combines `clsx` + `tailwind-merge` for class merging |

---

## 5. Backend — Python FastAPI Pipeline

### FastAPI Server (`main.py`)

**Runtime:** Python 3.12, uvicorn, port 8000

**Authentication:** All routes (except `/health`) require `X-Pipeline-Secret` HMAC header matching `PIPELINE_SECRET` env var.

**CORS:** Allows `NEXT_PUBLIC_APP_URL` origin.

**Endpoints:**

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Healthcheck (no auth) |
| `POST` | `/generate` | Main SSE pipeline endpoint |
| `POST` | `/generate` (with thread_id) | Resume LangGraph from checkpoint (HITL) |
| `POST` | `/compile-direct` | Compile LaTeX directly (called by compile_node internally) |
| `POST` | `/personas/generate` | Generate AI persona from plain-English description |
| `GET` | `/cache/status` | Check if jd_hash exists in resume_cache |

**SSE Streaming:**
- Returns `text/event-stream` response
- Each node completion emits: `data: {"node": "node_name", "state": {...}}\n\n`
- Final message: `data: [DONE]\n\n`
- Thread ID in response header: `X-Thread-ID`
- Filtered to `_STREAM_NODES` set (not all internal LangGraph events)

**Service Bus Consumer:**
- Background task in `main.py` listens to Azure Service Bus queue `compile-jobs`
- Each message: `{ job_id, latex_content, user_id }`
- Compiles via Tectonic → uploads to Azure Blob → writes result to Upstash Redis: `compile_result:{job_id}` (TTL 1hr)

---

### LangGraph Node Topology (`graph.py`)

**Checkpointer:** `MemorySaver()` (in-process; TODO: swap to Redis for multi-worker production)

**Full graph topology:**

```
[START]
   │
   ▼
ingest_node
   │
   ▼
embed_and_cache_node
   │
   ├─ [cache_hit = True] ──────────────────────────────────────► [END]
   │   (returns pdf_url, latex_output from Supabase)
   │
   └─ [cache_hit = False]
        │
        ▼
   analyze_latex_node
        │
        ▼
   generate_node ◄──────────────────────────────────────────────────────┐
        │                                                                 │
        ▼                                                                 │
   [fan_out_to_personas]  ← returns list[Send("critique_persona", ...)]  │
        │                   (one per selected persona ID)                 │
        ▼                                                                 │
   critique_persona × N  (parallel)                                      │
        │   └ accumulates into critique_results via operator.add         │
        ▼                                                                 │
   debate_node                                                            │
        │   (N parallel debate rounds + 1 consensus synthesis)           │
        ▼                                                                 │
   human_review_node  ← interrupt() pauses graph here                    │
        │                                                                 │
        ├─ [decision = "regen"] ──────────────────────────────────────────┘
        │   (re-enters generate_node with blocking_issues prepended)
        │
        └─ [decision = "approve" | "edit"]
              │
              ▼
         compile_node  ◄──────────────────────────────────────┐
              │                                                │
              ├─ [compile_error set] ──────────────► [END]    │
              ├─ [overflow_error set] ─────────────► [END]    │
              ├─ [page_count > 1] ──────────────────────────► compress_latex_node
              │                                                │
              └─ [page_count == 1]                            │
                    │                                          │
                    ▼                                          │
              cache_and_store_node                             │
                    │                 compress_latex_node ─────┘
                    ▼                 (max 2 attempts; overflow_error on 3rd)
                  [END]
```

**Key LangGraph patterns used:**
- `Send()` — fan-out parallel agents (critique)
- `Annotated[list[CritiqueResult], operator.add]` — automatic result accumulation
- `interrupt()` — HITL checkpoint (no `interrupt_before` needed)
- `Command(resume={...})` — resume from checkpoint with user decision
- `MemorySaver` — in-process state checkpointing

---

### Node-by-Node Breakdown

#### `ingest_node`
- Validates JD length (50–8,000 chars), strips null bytes and control chars
- Validates LaTeX contains `\begin{document}`
- Validates all selected persona IDs have a corresponding `.md` file in `pipeline/personas/`

#### `embed_and_cache_node` (cache.py)
1. **Compress JD** via LLMLingua-2 (`microsoft/llmlingua-2-xlm-roberta-large-meetingbank`, 50% rate, force-keep job keywords)
2. **SHA-256 hash** the compressed JD
3. **L1 lookup** — exact hash match in Supabase `resume_cache`
4. **L2 lookup** — embed via OpenAI `text-embedding-3-small` → cosine similarity ≥ 0.92 via `match_jd_cache` RPC
5. **Cache hit** → returns `pdf_url`, `latex_output`, `cache_hit=True` → graph ends
6. **Cache miss** → returns `jd_hash`, `jd_embedding`, `cache_hit=False` → continues

#### `analyze_latex_node`
- Pure regex: extracts bullet count, avg words/bullet, section headers, keyword gaps (JD terms missing from LaTeX, capped at 10), total word count
- No LLM call; feeds context into `generate_node` prompt

#### `generate_node`
- **Primary:** Claude Sonnet 4.6 via Instructor → `LaTeXOutput` (validated Pydantic model)
- **Fallback:** GPT-4o via Instructor if primary fails
- On regen: prepends `consensus.blocking_issues` to prompt
- Validates: `\begin{document}` present, word_count ≤ 600, format in {STAR, XYZ, CAR}

#### `critique_persona` (fan-out via Send())
- `fan_out_to_personas()` returns `[Send("critique_persona", PersonaState), ...]` — one per selected persona
- Each worker: loads persona `.md` as system prompt → Claude Sonnet 4.6 → `CritiqueResult`
- Belt-and-suspenders AI slop detection: if 3+ slop phrases found in generated LaTeX, `ai_slop_detected=True` regardless of LLM's own flag
- All results accumulated in `critique_results` via `operator.add`

#### `debate_node`
1. **Debate rounds** (parallel via `asyncio.gather`): each persona reads other personas' top 3 flags → Claude → `DebateRound`
2. **Consensus synthesis**: all critiques + debate rounds → Claude → `DebateConsensus`
   - `blocking_issues` = issues flagged by 2+ personas
   - `optional_improvements` = issues flagged by 1 persona
3. Resets `critique_results = []` so regen paths start fresh

#### `human_review_node`
- Calls `interrupt(payload)` where payload = `{ latex, consensus, critique_results }`
- Graph pauses; LangGraph checkpoints the full state
- Frontend receives interrupt payload in the SSE stream
- Frontend POSTs back with `human_decision` + optional `edited_latex` to resume

#### `compile_node`
- POSTs to `http://localhost:8000/compile-direct` (self-call within Container App)
- Uses `edited_latex` if user edited, else `latex_output.full_latex`
- Returns `pdf_url` (Azure Blob SAS URL), `page_count`
- Routes: error → END, overflow → END, >1 page → compress, 1 page → cache_and_store

#### `compress_latex_node`
- Attempt 1: reduce `\vspace{...}` → `\vspace{-2pt}`, `\itemsep` → `\itemsep -1pt`
- Attempt 2: additionally shrink font size (11pt→10.5pt, 10pt→9.5pt)
- Attempt 3+: sets `overflow_error=True`, routing ends the graph
- Loops back to `compile_node` after each attempt

#### `cache_and_store_node`
- Upserts into Supabase `resume_cache` (idempotent on `jd_hash`)
- Stores: `jd_hash`, `jd_embedding`, `latex_output` (JSONB), `pdf_url`, `critique_output` (JSONB), `user_id`

---

### Personas

Five AI personas defined as Markdown system prompts in `pipeline/personas/`:

| Persona ID | Archetype | Key Focus | Signature Flag |
|-----------|-----------|-----------|----------------|
| `ats_recruiter` | 11yr sourcing specialist, 200+ resumes/week | ATS parseability, keyword density, section labels, date formats | "The JD says 'Kubernetes' and the resume says 'container orchestration'. The ATS doesn't know those are the same." |
| `faang_bar_raiser` | Former Amazon Principal, 14yr Amazon/Google | Quantified impact, ownership signals, scope clarity, career trajectory | "Show me the number. What moved? By how much? Because of what you specifically did?" |
| `principal_engineer` | 18yr distributed systems, Stripe/Airbnb staff | Technical specificity, architecture tradeoffs, stack currency, scale indicators | "What was your pod eviction policy, and why did you choose that over the alternative?" |
| `startup_cto` | 3-time CTO, Series B SaaS | Shipping velocity, end-to-end ownership, bias for action, founder mindset | "Did you build it and ship it yourself? Because that's what 'senior engineer' means here." |
| `ai_ml_researcher` | PhD-level ML, 9yr, 14 papers | Training vs. API wrapper distinction, eval rigor, data provenance, model architecture | "You 'built an AI system.' Did you train anything, or did you write a prompt?" |

Personas can also be AI-generated at runtime via `POST /personas/generate` and stored in the Supabase `personas` table.

---

## 6. Database — Supabase (PostgreSQL + pgvector)

**Extensions:** `pgvector` (1536-dim embeddings, HNSW index)

### Table: `resume_cache`

Primary caching table. Stores compiled resumes keyed by JD hash.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID PK | Unique cache entry |
| `jd_hash` | TEXT UNIQUE | SHA-256 of compressed JD (fast exact lookup) |
| `jd_embedding` | vector(1536) | OpenAI embedding (semantic similarity lookup) |
| `latex_output` | JSONB | Full `LaTeXOutput` Pydantic model |
| `pdf_url` | TEXT | Azure Blob SAS URL to compiled PDF |
| `critique_output` | JSONB | `CritiqueResult[]` from critique phase |
| `user_id` | UUID → auth.users | Creator |
| `hit_count` | INTEGER | Analytics: how many times cache was hit |
| `created_at` / `updated_at` | TIMESTAMPTZ | Auto-managed |

**Indexes:**
- `jd_hash` B-tree unique — O(log n) exact match
- `jd_embedding` HNSW (m=16, ef_construction=64, cosine ops) — fast approximate nearest neighbor

**RPC function:** `match_jd_cache(query_embedding, match_threshold=0.92, match_count=1)` — returns top semantic match above threshold.

### Table: `resume_sessions`

Stores per-user iteration history (generation rounds).

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID PK | Session ID |
| `user_id` | UUID → auth.users | Owner |
| `jd_text` | TEXT | Job description |
| `iterations` | JSONB | Array of `LaTeXOutput` objects |
| `final_output` | JSONB | Final approved output |

### Table: `personas`

Stores AI-generated or user-created persona definitions.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID PK | Record ID |
| `user_id` | UUID → auth.users | Creator |
| `name` | TEXT | Display name |
| `persona_id` | TEXT UNIQUE per user | Slug used by pipeline (e.g., `faang_bar_raiser`) |
| `markdown` | TEXT | Full persona system prompt in Markdown |
| `is_public` | BOOLEAN | Shareable with all users |

**RLS:** Users can only read/write their own rows. Public personas (`is_public=true`) are readable by all authenticated users.

---

## 7. Infrastructure & Deployment

### Azure Container App (`latex-compiler`)

**Where it runs:** Azure Container Apps, `resume-env` environment, `resume-optimizer-rg` resource group
**Image:** `resumeoptimizeracr.azurecr.io/latex-compiler:latest` (linux/amd64)
**Resources:** 1 CPU core, 2Gi RAM
**Scaling:** Consumption profile, min=0 (scale-to-zero), max=10 replicas
**Scale trigger:** Azure Service Bus queue `compile-jobs`, scale when messageCount ≥ 5

**What runs inside:** The same FastAPI server (`main.py`) + Tectonic + pypdf + storage.py. Two roles:
1. **HTTP server** — handles `POST /compile-direct` (called by `compile_node`)
2. **Service Bus consumer** — background task polls `compile-jobs` queue

**To redeploy after code changes:**
```bash
docker buildx build --platform linux/amd64 \
  -t resumeoptimizeracr.azurecr.io/latex-compiler:latest --push .

az containerapp update \
  --name latex-compiler \
  --resource-group resume-optimizer-rg \
  --image resumeoptimizeracr.azurecr.io/latex-compiler:latest
```

---

### Azure Service Bus

**Namespace:** `resume-optimizer-bus`
**Queue:** `compile-jobs`
**Tier:** Standard
**Used for:** Sending LaTeX compile jobs asynchronously to the Container App

**Message format:**
```json
{ "job_id": "uuid", "latex_content": "...", "user_id": "..." }
```

**Producer:** `pipeline/main.py` — `send_compile_job()` function
**Consumer:** Container App background task in `main.py`

---

### Azure Blob Storage

**Account:** `resumeoptimizerstor`
**Container:** `pdfs`
**Blob path:** `resumes/{job_id}.pdf`
**Access:** Private; SAS URLs generated with 2-hour read permission
**Used by:** `storage.py` — `upload_pdf(job_id, pdf_bytes)` → returns SAS URL
**Consumed by:** Frontend `ExportButton` and `PDFViewer` components (direct browser fetch)

---

### Upstash Redis

**Type:** Serverless Redis (REST API, scale-to-zero)
**Used for two purposes:**

1. **Session cache** (Next.js side, `lib/redis.ts`):
   - Key: `session:{threadId}`
   - Value: `{ startedAt, body }`
   - TTL: 1 hour
   - Set by `/api/generate` when a new thread starts

2. **Compile result polling** (pipeline side):
   - Key: `compile_result:{job_id}`
   - Value: `{ success, pdf_url, page_count, compile_log }`
   - TTL: 1 hour
   - Written by Container App after compiling via Service Bus job
   - Read by pipeline's `poll_compile_result()` function (polls every 1s, 30s timeout)

---

### Langfuse Observability

**Host:** `https://cloud.langfuse.com`
**Used by:** Python pipeline (all LLM calls traced), Next.js API routes (singleton client in `lib/langfuse.ts`)

**Traced spans in pipeline:**
- `generate_latex_resume` — Claude generation call (metadata: is_regen, model, ats_score, word_count)
- `critique_{persona_id}` — per-persona critique call
- `debate_{persona_id}` — per-persona debate round
- `debate_consensus` — consensus synthesis call
- Full trace per `/generate` request with `langfuse_trace_id` stored in `GraphState`

---

## 8. Full Data Flow — Request Lifecycle

### Phase 1: New Generation (Cache Miss)

```
Browser                    Next.js API             FastAPI Pipeline
──────                     ───────────             ────────────────
POST /api/generate         │                       │
  { jd_raw,                │                       │
    latex_input,           │                       │
    selected_persona_ids } │                       │
                           │                       │
                           ├─ POST /generate ─────►│
                           │   X-Pipeline-Secret   │
                           │                       ├─ ingest_node
                           │                       │   validate inputs
                           │                       │
                           │                       ├─ embed_and_cache_node
                           │                       │   LLMLingua compress JD
                           │                       │   SHA-256 hash
                           │                       │   Supabase L1 exact check
                           │                       │   OpenAI embed + L2 cosine check
                           │                       │   → cache miss
                           │                       │
                           │◄── SSE: ingest_node ──┤
                           │◄── SSE: embed_and..   │
                           │                       ├─ analyze_latex_node
                           │◄── SSE: analyze_..    │   regex: bullets, gaps
                           │                       │
                           │                       ├─ generate_node
                           │                       │   Claude Sonnet 4.6
                           │                       │   → LaTeXOutput
                           │◄── SSE: generate_node ┤
                           │                       │
                           │                       ├─ fan_out_to_personas
                           │                       │   Send() × N personas
                           │                       │
                           │                       ├─ critique_persona × N (parallel)
                           │                       │   Claude per persona → CritiqueResult
                           │◄── SSE: critique_... ─┤  (one event per persona)
                           │                       │
                           │                       ├─ debate_node
                           │                       │   asyncio.gather → DebateRound × N
                           │                       │   Claude → DebateConsensus
                           │◄── SSE: debate_node ──┤
                           │                       │
                           │                       ├─ human_review_node
                           │                       │   interrupt(payload)
                           │◄── SSE: [DONE] ───────┤  (payload = latex+consensus+critique)
                           │   X-Thread-ID header  │
                           │                       │  ← GRAPH PAUSED HERE
                           │
                           ├─ setSessionCache(     │
                           │    threadId, {body}) ─► Upstash Redis
                           │
Browser sees [DONE] with hitlPayload → navigates to /resume → HITLPanel shown
```

### Phase 2: HITL Decision

```
Browser (HITLPanel)        Next.js API             FastAPI Pipeline
───────────────────        ───────────             ────────────────
User clicks Approve        │                       │
(or Regen / Edit LaTeX)    │                       │
                           │                       │
POST /api/generate         │                       │
  { thread_id,             │                       │
    human_decision,        │                       │
    edited_latex? }        │                       │
                           ├─ POST /generate ─────►│
                           │   (thread_id present) │
                           │                       ├─ Command(resume={decision, latex})
                           │                       │   resumes from checkpoint
                           │                       │
                           │                       ├─ route_after_human:
                           │                       │   "regen" → generate_node (loops)
                           │                       │   "approve"/"edit" → compile_node
```

### Phase 3: Compile → Store → Done

```
FastAPI Pipeline                     Azure Services
────────────────                     ──────────────
compile_node                         │
  POST /compile-direct ─────────────►│  Container App (latex-compiler)
  { job_id, latex_content, user_id } │    Tectonic compiles LaTeX → PDF bytes
                                     │    pypdf counts pages
                                     │    upload to Azure Blob (resumes/{job_id}.pdf)
                                     │    generate 2hr SAS URL
  ◄── { pdf_url, page_count } ───────┘

[if page_count > 1]
compress_latex_node (regex vspace/itemsep/fontsize)
  → loops back to compile_node (max 2 attempts)

cache_and_store_node
  → Supabase upsert resume_cache (jd_hash, embedding, latex_output, pdf_url)

[END]

SSE: data: [DONE]
  (state contains pdf_url, latex_output)
```

### Cache Hit Path (Fast Path)

```
ingest_node → embed_and_cache_node
  → LLMLingua compress → SHA-256 hash
  → Supabase: exact hash match OR cosine similarity ≥ 0.92
  → cache_hit = True
  → graph ends immediately
  → SSE [DONE] with existing pdf_url + latex_output
```

---

## 9. Environment Variables

### Next.js Frontend (`.env.local`)

| Variable | Used By | Purpose |
|----------|---------|---------|
| `NEXT_PUBLIC_SUPABASE_URL` | `lib/supabase.ts` | Supabase project URL (public) |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | `lib/supabase.ts` | Supabase anon key (public, RLS enforced) |
| `SUPABASE_SERVICE_ROLE_KEY` | `lib/supabase.ts`, API routes | Supabase service role key (bypasses RLS) |
| `UPSTASH_REDIS_REST_URL` | `lib/redis.ts` | Upstash Redis REST endpoint |
| `UPSTASH_REDIS_REST_TOKEN` | `lib/redis.ts` | Upstash Redis auth token |
| `PIPELINE_URL` | `/api/generate`, `next.config.ts` | FastAPI backend URL (e.g. `http://localhost:8000`) |
| `PIPELINE_SECRET` | `/api/generate`, `/api/personas/generate` | Shared HMAC secret with pipeline |
| `NEXT_PUBLIC_APP_URL` | CORS configuration | App origin URL |
| `LANGFUSE_SECRET_KEY` | `lib/langfuse.ts` | Langfuse secret key |
| `LANGFUSE_PUBLIC_KEY` | `lib/langfuse.ts` | Langfuse public key |
| `LANGFUSE_HOST` | `lib/langfuse.ts` | Langfuse endpoint (default: cloud.langfuse.com) |

### Python Pipeline (`pipeline/.env`)

| Variable | Used By | Purpose |
|----------|---------|---------|
| `ANTHROPIC_API_KEY` | generate.py, critique.py, debate.py, main.py | Claude API key |
| `OPENAI_API_KEY` | generate.py (fallback), cache.py (embeddings) | OpenAI API key |
| `SUPABASE_URL` | cache.py, cache_and_store.py, main.py | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | cache.py, cache_and_store.py | Service role key (bypasses RLS) |
| `UPSTASH_REDIS_REST_URL` | main.py | Upstash Redis REST endpoint |
| `UPSTASH_REDIS_REST_TOKEN` | main.py | Upstash Redis auth token |
| `SERVICEBUS_CONN` | main.py | Azure Service Bus connection string |
| `SERVICEBUS_QUEUE` | main.py | Queue name (default: `compile-jobs`) |
| `AZURE_STORAGE_CONN` | storage.py | Azure Blob Storage connection string |
| `AZURE_STORAGE_ACCOUNT` | storage.py | Storage account name |
| `AZURE_STORAGE_KEY` | storage.py | Storage account key |
| `AZURE_STORAGE_CONTAINER` | storage.py | Blob container name (default: `pdfs`) |
| `PIPELINE_URL` | compile.py | Self-URL for /compile-direct call |
| `PIPELINE_SECRET` | main.py | Incoming HMAC secret for auth |
| `LANGFUSE_SECRET_KEY` | main.py spans | Langfuse tracing key |
| `LANGFUSE_PUBLIC_KEY` | main.py spans | Langfuse public key |
| `LANGFUSE_HOST` | main.py | Langfuse endpoint |
| `TECTONIC_CACHE_DIR` | compiler.py | TeX package cache (default: `/tmp/tectonic-cache`) |
| `NEXT_PUBLIC_APP_URL` | main.py CORS | Allowed frontend origin |

---

## 10. Service Linkage Map

This table shows exactly which code files connect to which services and why.

| Service | Connecting File(s) | How Connected | What It Does |
|---------|--------------------|---------------|--------------|
| **Supabase** (resume_cache) | `pipeline/nodes/cache.py` | `supabase` Python SDK | L1 exact + L2 semantic cache lookup |
| **Supabase** (resume_cache) | `pipeline/nodes/cache_and_store.py` | `supabase` Python SDK | Upsert final result after compile |
| **Supabase** (resume_cache) | `app/api/cache/route.ts` | `@supabase/supabase-js` | Cache hit check by jd_hash |
| **Supabase** (auth) | `app/api/personas/generate/route.ts` | `@supabase/supabase-js` | Resolve user from Bearer token |
| **Supabase** (personas) | `pipeline/main.py` | `supabase` Python SDK | Store AI-generated personas |
| **Azure Blob Storage** | `pipeline/storage.py` | `azure-storage-blob` SDK | Upload PDF, generate SAS URL |
| **Azure Blob Storage** | `components/ExportButton.tsx` | Direct `<a href>` link | Browser downloads PDF |
| **Azure Blob Storage** | `components/PDFViewer.tsx` | pdfjs-dist fetch | Render PDF in canvas |
| **Azure Service Bus** | `pipeline/main.py` | `azure-servicebus` SDK | Send + consume compile jobs |
| **Upstash Redis** (sessions) | `lib/redis.ts` | `@upstash/redis` REST SDK | Session cache threadId metadata |
| **Upstash Redis** (sessions) | `app/api/generate/route.ts` | `lib/redis.ts` | Set session on new thread |
| **Upstash Redis** (results) | `pipeline/main.py` | `upstash-redis` Python SDK | Write compile_result after Service Bus job |
| **Anthropic (Claude Sonnet 4.6)** | `pipeline/nodes/generate.py` | `instructor` + `langchain-anthropic` | Primary resume generation |
| **Anthropic (Claude Sonnet 4.6)** | `pipeline/nodes/critique.py` | `instructor` + `anthropic` | Per-persona critique |
| **Anthropic (Claude Sonnet 4.6)** | `pipeline/nodes/debate.py` | `instructor` + `anthropic` | Debate rounds + consensus |
| **Anthropic (Claude Sonnet 4.6)** | `pipeline/main.py` | `anthropic` SDK | Persona generation from description |
| **OpenAI (GPT-4o)** | `pipeline/nodes/generate.py` | `instructor` + `langchain-openai` | Fallback resume generation |
| **OpenAI (text-embedding-3-small)** | `pipeline/nodes/cache.py` | `openai` SDK | JD embedding for semantic cache |
| **Langfuse** | `pipeline/nodes/generate.py` | `langfuse` Python SDK | Trace generation span |
| **Langfuse** | `pipeline/nodes/critique.py` | `langfuse` Python SDK | Trace per-persona spans |
| **Langfuse** | `pipeline/nodes/debate.py` | `langfuse` Python SDK | Trace debate + consensus spans |
| **Langfuse** | `lib/langfuse.ts` | `langfuse` npm SDK | API route tracing (Next.js) |
| **FastAPI (compile-direct)** | `pipeline/nodes/compile.py` | `httpx` (self POST) | Call own endpoint to compile LaTeX |
| **FastAPI (generate)** | `app/api/generate/route.ts` | Node `fetch` SSE | Proxy pipeline stream to browser |

---

## 11. How to Run Everything Locally

### Prerequisites
- Node.js 20+, pnpm/npm
- Python 3.12, `uv` or `pip`
- Docker (for Container App testing)
- Azure CLI (for redeployments only)

### Step 1: Copy env files
```bash
cp .env.example .env.local          # Fill in all values
cp pipeline/.env.example pipeline/.env  # Fill in all values
```

### Step 2: Start the Python pipeline
```bash
cd pipeline
uv sync                             # or: pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Step 3: Start the Next.js frontend
```bash
# Root of project
npm install
npm run dev                         # Starts on http://localhost:3000 (Turbopack)
```

### Step 4: (Optional) Run tests
```bash
# Frontend
npm run test

# Backend
cd pipeline
pytest tests/ -v
```

### Step 5: (Optional) Build & push Container App image
The Container App (`latex-compiler`) is already live on Azure. Only needed when `pipeline/` code changes:
```bash
docker buildx build --platform linux/amd64 \
  -t resumeoptimizeracr.azurecr.io/latex-compiler:latest --push .

az containerapp update \
  --name latex-compiler \
  --resource-group resume-optimizer-rg \
  --image resumeoptimizeracr.azurecr.io/latex-compiler:latest
```

### Local vs. Production differences
| | Local | Production (Azure) |
|--|-------|-------------------|
| LaTeX compilation | `POST /compile-direct` to `localhost:8000` | Azure Container App via Service Bus or HTTP |
| State checkpoint | `MemorySaver` (in-process) | Should be Redis (TODO) |
| PDF storage | Azure Blob (same) | Azure Blob |
| Database | Supabase cloud (same) | Supabase cloud |

---

## 12. Testing Overview

### Frontend (Vitest + Testing Library)

| Suite | What's Tested | Count |
|-------|--------------|-------|
| `store/resumeStore.test.ts` | Zustand state mutations, history accumulation, reset, error handling | 8 tests |

### Backend (pytest + pytest-asyncio)

| Suite | What's Tested | Count |
|-------|--------------|-------|
| `tests/test_nodes.py` | `ingest_node` — input validation, persona loading, sanitization | 8 tests |
| `tests/test_schemas.py` | All Pydantic model constraints (word count, score ranges, LaTeX validity) | 18 tests |
| `tests/test_critique.py` | Fan-out, LLM mock, AI slop detection, persona ID override | 11 tests |
| `tests/test_debate.py` | Debate rounds, consensus synthesis, edge cases (1 persona, fallback) | 9 tests |
| `tests/test_compile_node.py` | Compile routing (error, multi-page, single-page), `edited_latex` preference | 9 tests |
| `tests/test_analyze_latex.py` | Regex analysis: bullets, sections, word count, keyword gaps | 12 tests |
| `tests/test_compress_latex.py` | Compression attempts 1-3, `overflow_error` trigger | 10 tests |
| `tests/test_human_review.py` | HITL decisions, routing (approve/regen/edit), interrupt payload | 9 tests |
| `test_compile.py` | Integration test for `/compile-direct` endpoint (manual, Docker required) | 1 test |

**Total: ~95 test cases**

---

## 13. Known Gaps & TODOs

| Area | Issue | Impact |
|------|-------|--------|
| **Checkpointer** | `MemorySaver` used in production — state lost on pod restart | HITL breaks if pod restarts between interrupt and resume |
| **Dead code** | `nodes/iterate.py`, `nodes/resolve.py` not connected to graph | Confusion; should be deleted |
| **SSE parsing duplication** | `page.tsx` and `HITLPanel.tsx` both contain identical SSE parsing logic | Maintenance burden |
| **Zustand persistence** | `latexOutput`, `critique`, `consensus` not persisted to localStorage | State lost on page refresh |
| **compile_node self-call** | `compile.py` POSTs to `localhost:8000/compile-direct` (self) — fragile in Container App | Could POST to `0.0.0.0` or use internal Service Bus routing instead |
| **Service Bus wire-up** | `nodes/compile.py` uses direct HTTP; Service Bus consumer in `main.py` is only partially wired to return results via Redis | `compile_node` doesn't use the queue path yet |
| **No auth on frontend** | Frontend doesn't require login; `user_id` is null in most Supabase writes | Cache entries not user-scoped |
| **Multi-worker LangGraph** | `MemorySaver` is single-process; cannot resume across different replicas | Must use Redis checkpointer before scaling past 1 replica |
