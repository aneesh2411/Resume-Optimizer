/**
 * POST /api/generate
 *
 * Streaming proxy: Next.js → FastAPI pipeline.
 *
 * - Forwards the request body to the Python FastAPI /generate endpoint
 * - Streams the SSE response back to the browser
 * - Exposes X-Thread-ID header so the client can resume iterations
 * - Stores thread_id in Upstash Redis for session tracking
 *
 * Runtime: nodejs (not edge) — required for streaming + long timeouts
 */

import { NextRequest } from "next/server";
import { setSessionCache } from "@/lib/redis";

export const runtime = "nodejs";
export const maxDuration = 120; // seconds — adjust per Vercel plan

export async function POST(req: NextRequest): Promise<Response> {
  const body: unknown = await req.json();

  const pipelineUrl = process.env.PIPELINE_URL ?? "http://localhost:8000";
  const pipelineSecret = process.env.PIPELINE_SECRET ?? "";

  let pipelineRes: Response;
  try {
    pipelineRes = await fetch(`${pipelineUrl}/generate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Pipeline-Secret": pipelineSecret,
      },
      body: JSON.stringify(body),
    });
  } catch (err) {
    console.error("[/api/generate] Pipeline unreachable:", err);
    return new Response(JSON.stringify({ error: "Pipeline service unavailable" }), {
      status: 503,
      headers: { "Content-Type": "application/json" },
    });
  }

  if (!pipelineRes.ok || !pipelineRes.body) {
    const errText = await pipelineRes.text().catch(() => "unknown error");
    console.error("[/api/generate] Pipeline error:", pipelineRes.status, errText);
    return new Response(JSON.stringify({ error: errText }), {
      status: pipelineRes.status,
      headers: { "Content-Type": "application/json" },
    });
  }

  const threadId = pipelineRes.headers.get("X-Thread-ID") ?? "";

  // Persist thread_id → session metadata in Redis for later use
  if (threadId) {
    void setSessionCache(threadId, {
      startedAt: new Date().toISOString(),
      body,
    }).catch((e) => console.warn("[/api/generate] Redis setex failed:", e));
  }

  // Forward the SSE stream verbatim
  const stream = new ReadableStream({
    async start(controller) {
      const reader = pipelineRes.body!.getReader();
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          controller.enqueue(value);
        }
      } catch (err) {
        console.error("[/api/generate] Stream read error:", err);
        controller.error(err);
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
      "X-Thread-ID": threadId,
      "X-Accel-Buffering": "no",
    },
  });
}
