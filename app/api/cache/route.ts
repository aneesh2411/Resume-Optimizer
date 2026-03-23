/**
 * GET /api/cache?jd_hash=<sha256>
 *
 * Check whether a JD SHA-256 hash has a cached resume result in Supabase.
 * Returns { cached: boolean, data: { id, hit_count, created_at } | null }
 */

import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase";

export const runtime = "nodejs";

export async function GET(req: NextRequest): Promise<NextResponse> {
  const jdHash = req.nextUrl.searchParams.get("jd_hash");

  if (!jdHash) {
    return NextResponse.json({ error: "jd_hash query parameter is required" }, { status: 400 });
  }

  try {
    const supabase = createSupabaseServerClient();
    const { data, error } = await supabase
      .from("resume_cache")
      .select("id, hit_count, created_at")
      .eq("jd_hash", jdHash)
      .maybeSingle();

    if (error) {
      console.error("[/api/cache] Supabase error:", error);
      return NextResponse.json({ error: "Database query failed" }, { status: 500 });
    }

    return NextResponse.json({ cached: !!data, data });
  } catch (err) {
    console.error("[/api/cache] Unexpected error:", err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
