-- 002_personas_table.sql
-- AI-generated and user-created persona definitions

CREATE TABLE IF NOT EXISTS public.personas (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    persona_id  TEXT NOT NULL,          -- slug used in pipeline (e.g. "my_cto")
    markdown    TEXT NOT NULL,
    is_public   BOOLEAN DEFAULT false,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS personas_user_id_persona_id_idx
    ON public.personas (user_id, persona_id);

ALTER TABLE public.personas ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage their own personas"
    ON public.personas FOR ALL
    USING (auth.uid() = user_id);

CREATE POLICY "Public personas are readable by all authenticated users"
    ON public.personas FOR SELECT
    USING (is_public = true);
