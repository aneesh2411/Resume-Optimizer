"use client";

/**
 * HITLPanel — Human-in-the-loop decision panel.
 *
 * Shown when human_review_node pauses the graph via interrupt().
 * Three actions:
 *   - Approve & Compile: sends human_decision = "approve"
 *   - Regenerate: sends human_decision = "regen"
 *   - Edit & Compile: switches Monaco to editable, then sends human_decision = "edit" + edited_latex
 */

import { useState, useCallback } from "react";
import { useResumeStore } from "@/store/resumeStore";
import { MonacoEditor } from "@/components/MonacoEditor";
import type { LaTeXOutput, DebateConsensus, CritiqueResult } from "@/store/resumeStore";

interface HITLPanelProps {
  latex: string;
  consensus: DebateConsensus | null;
  critique: CritiqueResult[];
  threadId: string;
  onComplete: () => void;
}

export function HITLPanel({ latex, consensus, threadId, onComplete }: HITLPanelProps) {
  const [editMode, setEditMode] = useState(false);
  const [editedLatex, setEditedLatex] = useState(latex);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const {
    setStreaming,
    setCurrentNode,
    setLatexOutput,
    setPdfUrl,
    setCritique,
    setConsensus,
    setHitlPayload,
    setError: setStoreError,
    jd,
    latexInput,
    personaIds,
  } = useResumeStore();

  const sendDecision = useCallback(
    async (decision: "approve" | "regen" | "edit") => {
      setSubmitting(true);
      setError(null);

      try {
        const res = await fetch("/api/generate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            jd_raw: jd,
            latex_input: latexInput,
            selected_persona_ids: personaIds,
            thread_id: threadId,
            human_decision: decision,
            edited_latex: decision === "edit" ? editedLatex : undefined,
          }),
        });

        if (!res.ok || !res.body) {
          throw new Error(`Pipeline error: ${res.status}`);
        }

        setStreaming(true);
        setHitlPayload(null);

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
                  latex_output?: LaTeXOutput;
                  pdf_url?: string;
                  critique_results?: CritiqueResult[];
                  consensus?: DebateConsensus;
                  hitl?: { latex: string | null; consensus: DebateConsensus | null; critique_results: CritiqueResult[] };
                  error?: string;
                };
              };

              if (event.error) throw new Error(event.error);
              if (event.node) setCurrentNode(event.node);
              if (event.state?.error) throw new Error(event.state.error);
              if (event.state?.latex_output) setLatexOutput(event.state.latex_output);
              if (event.state?.pdf_url) setPdfUrl(event.state.pdf_url);
              if (event.state?.critique_results?.length) setCritique(event.state.critique_results);
              if (event.state?.consensus) setConsensus(event.state.consensus);

              // HITL interrupt — graph paused again (regen path)
              if (event.node === "human_review_node" && event.state?.hitl) {
                setHitlPayload(event.state.hitl);
              }
            } catch {
              // Skip malformed SSE lines
            }
          }
        }

        onComplete();
      } catch (err) {
        setError(String(err));
        setStoreError(String(err));
      } finally {
        setSubmitting(false);
        setStreaming(false);
        setCurrentNode(null);
      }
    },
    [
      jd, latexInput, personaIds, threadId, editedLatex,
      setStreaming, setCurrentNode, setLatexOutput, setPdfUrl,
      setCritique, setConsensus, setHitlPayload, setStoreError, onComplete,
    ]
  );

  return (
    <div className="border rounded-lg bg-white overflow-hidden">
      <div className="px-4 py-3 border-b bg-muted/30">
        <h3 className="text-sm font-semibold text-foreground">Human Review</h3>
        <p className="text-xs text-muted-foreground mt-0.5">
          Review the generated LaTeX below and choose an action.
        </p>
      </div>

      {/* Blocking issues reminder */}
      {consensus?.blocking_issues && consensus.blocking_issues.length > 0 && (
        <div className="px-4 py-3 border-b bg-red-50">
          <p className="text-xs font-semibold text-red-600 uppercase tracking-wide mb-1">
            Issues to address before approving
          </p>
          <ul className="space-y-1">
            {consensus.blocking_issues.map((issue, i) => (
              <li key={i} className="text-xs text-red-700 flex gap-1.5">
                <span className="shrink-0">🚫</span>
                <span>{issue}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Monaco editor */}
      <div className="p-4">
        <MonacoEditor
          value={editMode ? editedLatex : latex}
          onChange={setEditedLatex}
          readOnly={!editMode}
          height="400px"
        />
      </div>

      {error && (
        <div className="px-4 py-2 text-sm text-red-600 bg-red-50 border-t">
          {error}
        </div>
      )}

      {/* Action buttons */}
      <div className="px-4 py-3 border-t flex flex-wrap gap-2">
        {!editMode ? (
          <>
            <button
              onClick={() => sendDecision("approve")}
              disabled={submitting}
              className="flex-1 py-2 px-4 text-sm font-medium rounded-lg bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {submitting ? "Processing…" : "Approve & Compile"}
            </button>
            <button
              onClick={() => sendDecision("regen")}
              disabled={submitting}
              className="flex-1 py-2 px-4 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Regenerate
            </button>
            <button
              onClick={() => setEditMode(true)}
              disabled={submitting}
              className="flex-1 py-2 px-4 text-sm font-medium rounded-lg border bg-white text-foreground hover:bg-muted/50 disabled:opacity-50 transition-colors"
            >
              Edit LaTeX
            </button>
          </>
        ) : (
          <>
            <button
              onClick={() => sendDecision("edit")}
              disabled={submitting}
              className="flex-1 py-2 px-4 text-sm font-medium rounded-lg bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {submitting ? "Processing…" : "Compile Edited LaTeX"}
            </button>
            <button
              onClick={() => { setEditMode(false); setEditedLatex(latex); }}
              disabled={submitting}
              className="py-2 px-4 text-sm font-medium rounded-lg border bg-white text-foreground hover:bg-muted/50 disabled:opacity-50 transition-colors"
            >
              Cancel
            </button>
          </>
        )}
      </div>
    </div>
  );
}
