/**
 * lib/langfuse.ts — Langfuse observability client for Next.js API routes.
 *
 * Singleton pattern: one Langfuse instance per process to avoid repeated
 * initialisation and ensure flushed traces on shutdown.
 */

import Langfuse from "langfuse";

let _langfuse: Langfuse | null = null;

export function getLangfuse(): Langfuse {
  if (!_langfuse) {
    _langfuse = new Langfuse({
      secretKey: process.env.LANGFUSE_SECRET_KEY!,
      publicKey: process.env.LANGFUSE_PUBLIC_KEY!,
      baseUrl: process.env.LANGFUSE_HOST ?? "https://cloud.langfuse.com",
    });
  }
  return _langfuse;
}
