/**
 * lib/supabase.ts — Supabase client factories.
 *
 * Two clients:
 * - Browser client: uses anon key, subject to RLS — safe to use in React components
 * - Server client: uses service role key, bypasses RLS — only for API routes / server actions
 */

import { createBrowserClient } from "@supabase/ssr";
import { createClient, SupabaseClient } from "@supabase/supabase-js";

// ── Browser client (React components) ────────────────────────────────────────

export function createSupabaseBrowserClient(): SupabaseClient {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  );
}

// ── Server client (API routes only — NEVER import in client components) ───────

export function createSupabaseServerClient(): SupabaseClient {
  if (!process.env.SUPABASE_SERVICE_ROLE_KEY) {
    throw new Error("SUPABASE_SERVICE_ROLE_KEY is not set");
  }
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY,
    {
      auth: {
        persistSession: false,
        autoRefreshToken: false,
      },
    }
  );
}
