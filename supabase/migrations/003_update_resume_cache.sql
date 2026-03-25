-- 003_update_resume_cache.sql
-- Add user_id and pdf_url to resume_cache for the LaTeX-first pipeline

ALTER TABLE public.resume_cache
    ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id),
    ADD COLUMN IF NOT EXISTS pdf_url TEXT;

CREATE INDEX IF NOT EXISTS resume_cache_user_id_idx
    ON public.resume_cache (user_id);

-- latex_output column replaces the old resume_output column
-- Adding it conditionally so this is idempotent
ALTER TABLE public.resume_cache
    ADD COLUMN IF NOT EXISTS latex_output JSONB;

COMMENT ON COLUMN public.resume_cache.pdf_url
    IS 'Azure Blob URL of the compiled PDF; set by cache_and_store_node after successful compilation';

COMMENT ON COLUMN public.resume_cache.latex_output
    IS 'Serialised LaTeXOutput Pydantic model (full_latex, sections, format_used, ats_score_estimate, word_count)';
