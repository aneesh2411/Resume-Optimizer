"use client";

/**
 * app/page.tsx — Landing page.
 *
 * Users paste:
 * 1. A job description (required)
 * 2. Their existing resume (optional, used as context for tailoring)
 *
 * On submit:
 * - Calls POST /api/generate (SSE stream)
 * - Parses events to update Zustand state
 * - Redirects to /resume once first draft + critique are ready
 */

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useResumeStore } from "@/store/resumeStore";
import type { ResumeOutput, CritiqueResult, ConflictResolution } from "@/store/resumeStore";

// Node-to-label map for the progress indicator
const NODE_LABELS: Record<string, string> = {
  ingest: "Parsing inputs…",
  compress: "Compressing job description…",
  embed_and_cache: "Checking semantic cache…",
  generate: "Generating tailored resume…",
  critique: "Running multi-persona critique…",
  resolve: "Synthesising feedback…",
};

export default function LandingPage() {
  const [jd, setJd] = useState("");
  const [resumeText, setResumeText] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  const router = useRouter();

  const {
    setJobDescription,
    setThreadId,
    setStreaming,
    setCurrentNode,
    setDraft,
    setCritique,
    setResolution,
    setError,
    isStreaming,
    currentNode,
    reset,
  } = useResumeStore();

  const handleSubmit = useCallback(async () => {
    if (!jd.trim()) {
      setLocalError("Please paste a job description.");
      return;
    }

    setLocalError(null);
    reset();
    setJobDescription(jd);
    setStreaming(true);
    setCurrentNode("ingest");

    let threadId = "";
    let hasDraft = false;
    let hasCritique = false;

    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          jd_raw: jd,
          resume_raw: resumeText.trim() || null,
        }),
      });

      if (!res.ok || !res.body) {
        throw new Error(`Pipeline error: ${res.status}`);
      }

      threadId = res.headers.get("X-Thread-ID") ?? "";
      if (threadId) setThreadId(threadId);

      const decoder = new TextDecoder();
      const reader = res.body.getReader();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6).trim();
          if (payload === "[DONE]") break;

          try {
            const event = JSON.parse(payload) as {
              node?: string;
              error?: string;
              state?: {
                resume_output?: ResumeOutput;
                critique_results?: CritiqueResult[];
                conflict_resolution?: ConflictResolution;
                error?: string;
              };
            };

            if (event.error) {
              throw new Error(event.error);
            }

            if (event.node) {
              setCurrentNode(event.node);
            }

            if (event.state?.error) {
              throw new Error(event.state.error);
            }

            if (event.state?.resume_output) {
              setDraft(event.state.resume_output);
              hasDraft = true;
            }

            if (event.state?.critique_results?.length) {
              setCritique(event.state.critique_results);
              hasCritique = true;
            }

            if (event.state?.conflict_resolution) {
              setResolution(event.state.conflict_resolution);
            }
          } catch (parseErr) {
            // Skip malformed SSE lines
          }
        }

        // Redirect as soon as we have both draft + critique
        if (hasDraft && hasCritique) {
          router.push("/resume");
          break;
        }
      }

      // If we finished streaming without redirecting (e.g. cache hit with no critique)
      if (hasDraft) {
        router.push("/resume");
      }
    } catch (err) {
      setError(String(err));
      setLocalError(String(err));
    } finally {
      setStreaming(false);
      setCurrentNode(null);
    }
  }, [
    jd,
    resumeText,
    reset,
    setJobDescription,
    setThreadId,
    setStreaming,
    setCurrentNode,
    setDraft,
    setCritique,
    setResolution,
    setError,
    router,
  ]);

  const progressLabel = currentNode ? (NODE_LABELS[currentNode] ?? `${currentNode}…`) : null;

  return (
    <main className="min-h-screen bg-gradient-to-b from-slate-50 to-white">
      <div className="max-w-3xl mx-auto py-16 px-4 space-y-8">
        {/* Header */}
        <div className="text-center space-y-3">
          <h1 className="text-4xl font-bold tracking-tight text-foreground">
            Resume Optimizer
          </h1>
          <p className="text-lg text-muted-foreground max-w-xl mx-auto">
            Paste a job description and get a single-page ATS-optimized resume
            with critique from a recruiter, hiring manager, and industry expert.
          </p>
        </div>

        {/* Feature badges */}
        <div className="flex flex-wrap justify-center gap-2 text-xs">
          {[
            "Single-page A4 guarantee",
            "Multi-persona AI critique",
            "ATS keyword optimisation",
            "STAR / XYZ / CAR format",
            "Semantic cache (instant on repeat JDs)",
          ].map((f) => (
            <span
              key={f}
              className="px-3 py-1 rounded-full border bg-white text-muted-foreground"
            >
              {f}
            </span>
          ))}
        </div>

        {/* Form */}
        <div className="space-y-4">
          <div className="space-y-1.5">
            <label
              htmlFor="jd-input"
              className="text-sm font-medium text-foreground"
            >
              Job Description{" "}
              <span className="text-red-500">*</span>
            </label>
            <textarea
              id="jd-input"
              className="w-full min-h-[200px] p-3 text-sm border rounded-lg bg-background resize-y focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
              placeholder="Paste the full job description here…"
              value={jd}
              onChange={(e) => setJd(e.target.value)}
              disabled={isStreaming}
              rows={10}
            />
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="resume-input"
              className="text-sm font-medium text-foreground"
            >
              Your Existing Resume{" "}
              <span className="text-muted-foreground text-xs">(optional)</span>
            </label>
            <textarea
              id="resume-input"
              className="w-full min-h-[150px] p-3 text-sm border rounded-lg bg-background resize-y focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
              placeholder="Paste your current resume (plain text) for personalised tailoring…"
              value={resumeText}
              onChange={(e) => setResumeText(e.target.value)}
              disabled={isStreaming}
              rows={7}
            />
            <p className="text-xs text-muted-foreground">
              Without a resume, the AI will generate one from scratch based on the JD.
            </p>
          </div>

          {/* Error */}
          {localError && (
            <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {localError}
            </p>
          )}

          {/* Progress */}
          {isStreaming && progressLabel && (
            <div className="flex items-center gap-3 text-sm text-muted-foreground bg-blue-50 border border-blue-200 rounded-lg px-3 py-2">
              <span className="animate-spin h-4 w-4 border-2 border-primary border-t-transparent rounded-full shrink-0" />
              <span>{progressLabel}</span>
            </div>
          )}

          {/* Submit */}
          <button
            onClick={handleSubmit}
            disabled={isStreaming || !jd.trim()}
            className="w-full py-3 px-6 text-sm font-semibold rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isStreaming ? "Optimizing…" : "Optimize Resume"}
          </button>
        </div>
      </div>
    </main>
  );
}
