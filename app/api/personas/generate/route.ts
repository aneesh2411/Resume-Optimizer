/**
 * POST /api/personas/generate
 *
 * Proxy to the pipeline /personas/generate endpoint.
 * Attaches X-User-ID from the Supabase session so the pipeline can
 * associate the generated persona with the authenticated user.
 */

import { NextRequest } from "next/server";
import { createClient } from "@supabase/supabase-js";

export const runtime = "nodejs";

export async function POST(req: NextRequest): Promise<Response> {
  const body: unknown = await req.json();

  // Resolve the calling user via service-role key (server-side)
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY ?? "";
  const supabase = createClient(supabaseUrl, serviceKey);

  // Read user from Authorization header (Bearer <access_token>)
  const authHeader = req.headers.get("Authorization") ?? "";
  const accessToken = authHeader.replace(/^Bearer\s+/, "");
  let userId: string | null = null;
  if (accessToken) {
    const { data } = await supabase.auth.getUser(accessToken);
    userId = data.user?.id ?? null;
  }

  const pipelineUrl = process.env.PIPELINE_URL ?? "http://localhost:8000";
  const pipelineSecret = process.env.PIPELINE_SECRET ?? "";

  let pipelineRes: Response;
  try {
    pipelineRes = await fetch(`${pipelineUrl}/personas/generate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Pipeline-Secret": pipelineSecret,
        ...(userId ? { "X-User-ID": userId } : {}),
      },
      body: JSON.stringify(body),
    });
  } catch (err) {
    console.error("[/api/personas/generate] Pipeline unreachable:", err);
    return new Response(JSON.stringify({ error: "Pipeline service unavailable" }), {
      status: 503,
      headers: { "Content-Type": "application/json" },
    });
  }

  const data = await pipelineRes.json().catch(() => ({}));
  return new Response(JSON.stringify(data), {
    status: pipelineRes.status,
    headers: { "Content-Type": "application/json" },
  });
}
