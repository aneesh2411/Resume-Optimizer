-- ============================================================
-- 001_pgvector.sql
-- Resume Optimizer — semantic cache + session history
-- ============================================================

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;

-- ── Resume cache (semantic deduplication) ───────────────────
CREATE TABLE IF NOT EXISTS public.resume_cache (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    jd_hash         TEXT NOT NULL,               -- SHA-256 of raw JD text (exact match fast path)
    jd_embedding    vector(1536) NOT NULL,        -- text-embedding-3-small output
    resume_output   JSONB NOT NULL,              -- serialized ResumeOutput
    critique_output JSONB,                       -- serialized CritiqueResult[] (nullable)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    hit_count       INTEGER NOT NULL DEFAULT 0   -- analytics
);

-- HNSW index for approximate nearest-neighbour cosine search
-- (faster than IVFFlat: no training required, good recall at all dataset sizes)
CREATE INDEX IF NOT EXISTS resume_cache_embedding_idx
    ON public.resume_cache
    USING hnsw (jd_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Exact hash lookup (B-tree)
CREATE UNIQUE INDEX IF NOT EXISTS resume_cache_jd_hash_idx
    ON public.resume_cache (jd_hash);

-- ── Resume sessions (iteration history per user) ─────────────
CREATE TABLE IF NOT EXISTS public.resume_sessions (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    jd_text      TEXT NOT NULL,
    iterations   JSONB NOT NULL DEFAULT '[]'::jsonb,  -- array of ResumeOutput
    final_output JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS resume_sessions_user_idx
    ON public.resume_sessions (user_id);

-- ── Row-level security ────────────────────────────────────────
ALTER TABLE public.resume_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.resume_sessions ENABLE ROW LEVEL SECURITY;

-- Service role bypasses RLS (used by the Python pipeline)
CREATE POLICY "service_role_bypass_cache" ON public.resume_cache
    USING (auth.role() = 'service_role');

CREATE POLICY "service_role_bypass_sessions" ON public.resume_sessions
    USING (auth.role() = 'service_role');

-- Authenticated users may read/write their own sessions
CREATE POLICY "users_own_sessions" ON public.resume_sessions
    FOR ALL USING (auth.uid() = user_id);

-- ── Semantic similarity search RPC ───────────────────────────
-- Returns cache rows whose cosine similarity to the query exceeds the threshold.
-- Called from the Python pipeline's embed_and_cache_node.
CREATE OR REPLACE FUNCTION public.match_jd_cache(
    query_embedding  vector(1536),
    match_threshold  FLOAT  DEFAULT 0.92,
    match_count      INT    DEFAULT 1
)
RETURNS TABLE (
    id              UUID,
    resume_output   JSONB,
    critique_output JSONB,
    similarity      FLOAT
)
LANGUAGE SQL STABLE SECURITY DEFINER
AS $$
    SELECT
        id,
        resume_output,
        critique_output,
        1 - (jd_embedding <=> query_embedding) AS similarity
    FROM public.resume_cache
    WHERE 1 - (jd_embedding <=> query_embedding) > match_threshold
    ORDER BY jd_embedding <=> query_embedding
    LIMIT match_count;
$$;

-- ── Trigger: auto-update updated_at ───────────────────────────
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER resume_cache_updated_at
    BEFORE UPDATE ON public.resume_cache
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER resume_sessions_updated_at
    BEFORE UPDATE ON public.resume_sessions
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
