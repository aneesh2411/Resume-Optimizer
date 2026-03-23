"use client";

/**
 * IterationInput — user feedback form for resume refinement.
 *
 * Renders a textarea + "Regenerate" button.
 * On submit: sends thread_id + feedback to POST /api/generate,
 * parses the SSE stream, and updates Zustand state.
 *
 * Also provides an "Approve & Export" path via the ExportButton.
 */

import { useState, useCallback } from "react";
import { useResumeStore } from "@/store/resumeStore";
import type { ResumeOutput, CritiqueResult, ConflictResolution } from "@/store/resumeStore";

// ── SSE parsing helper ────────────────────────────────────────────────────────

interface SSEEvent {
  node?: string;
  state?: {
    resume_output?: ResumeOutput;
    critique_results?: CritiqueResult[];
    conflict_resolution?: ConflictResolution;
    error?: string;
  };
  error?: string;
}

async function consumeSSEStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  callbacks: {
    onNode: (node: string) => void;
    onDraft: (draft: ResumeOutput) => void;
    onCritique: (critique: CritiqueResult[]) => void;
    onResolution: (resolution: ConflictResolution) => void;
    onError: (error: string) => void;
  }
): Promise<void> {
  const decoder = new TextDecoder();
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
      if (payload === "[DONE]") return;

      try {
        const event: SSEEvent = JSON.parse(payload);

        if (event.error) {
          callbacks.onError(event.error);
          return;
        }

        if (event.node) {
          callbacks.onNode(event.node);
        }

        if (event.state?.resume_output) {
          callbacks.onDraft(event.state.resume_output);
        }

        if (event.state?.critique_results?.length) {
          callbacks.onCritique(event.state.critique_results);
        }

        if (event.state?.conflict_resolution) {
          callbacks.onResolution(event.state.conflict_resolution);
        }

        if (event.state?.error) {
          callbacks.onError(event.state.error);
        }
      } catch {
        // Non-JSON line — skip
      }
    }
  }
}

// ── Component ────────────────────────────────────────────────────────────────

export function IterationInput() {
  const [feedback, setFeedback] = useState("");

  const {
    threadId,
    jobDescription,
    isStreaming,
    setStreaming,
    setCurrentNode,
    setDraft,
    setCritique,
    setResolution,
    setError,
  } = useResumeStore();

  const handleRegenerate = useCallback(async () => {
    if (!feedback.trim() || isStreaming) return;

    setStreaming(true);
    setError(null);
    setCurrentNode("ingest");

    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          jd_raw: jobDescription,
          thread_id: threadId,
          user_iteration_feedback: feedback,
        }),
      });

      if (!res.ok || !res.body) {
        const text = await res.text().catch(() => "Unknown error");
        throw new Error(text);
      }

      await consumeSSEStream(res.body.getReader(), {
        onNode: setCurrentNode,
        onDraft: setDraft,
        onCritique: setCritique,
        onResolution: setResolution,
        onError: (e) => setError(e),
      });

      setFeedback("");
    } catch (err) {
      setError(String(err));
    } finally {
      setStreaming(false);
      setCurrentNode(null);
    }
  }, [
    feedback,
    isStreaming,
    jobDescription,
    threadId,
    setStreaming,
    setCurrentNode,
    setDraft,
    setCritique,
    setResolution,
    setError,
  ]);

  return (
    <div className="space-y-3">
      <div>
        <label
          htmlFor="iteration-feedback"
          className="text-sm font-medium text-foreground block mb-1.5"
        >
          Refine your resume
        </label>
        <textarea
          id="iteration-feedback"
          className="w-full min-h-[100px] p-3 text-sm border rounded-lg bg-background resize-y focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
          placeholder='E.g. "Add more emphasis on Python skills", "Make the summary more concise", "Highlight leadership experience"'
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          disabled={isStreaming}
          rows={4}
        />
      </div>

      <button
        onClick={handleRegenerate}
        disabled={isStreaming || !feedback.trim() || !threadId}
        className="w-full py-2.5 px-4 text-sm font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {isStreaming ? (
          <span className="flex items-center justify-center gap-2">
            <span className="animate-spin h-3.5 w-3.5 border-2 border-current border-t-transparent rounded-full" />
            Regenerating…
          </span>
        ) : (
          "Regenerate Resume"
        )}
      </button>

      {!threadId && (
        <p className="text-xs text-muted-foreground text-center">
          Generate a resume first to enable iteration
        </p>
      )}
    </div>
  );
}
