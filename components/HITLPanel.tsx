"use client";

/**
 * HITLPanel — Human-in-the-loop decision gate.
 *
 * Shown when human_review_node pauses the graph via interrupt().
 * Three actions rendered as decision cards:
 *   - Approve & Compile  → human_decision = "approve"
 *   - Regenerate         → human_decision = "regen"
 *   - Edit LaTeX         → opens Monaco editor, then human_decision = "edit" + edited_latex
 */

import { useState, useCallback } from "react";
import { useResumeStore } from "@/store/resumeStore";
import { MonacoEditor } from "@/components/MonacoEditor";
import { cn } from "@/lib/utils";
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
  const [showLatex, setShowLatex] = useState(false);
  const [editedLatex, setEditedLatex] = useState(latex);
  const [submitting, setSubmitting] = useState(false);
  const [activeAction, setActiveAction] = useState<"approve" | "regen" | "edit" | null>(null);
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
      setActiveAction(decision);
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
        setActiveAction(null);
      }
    },
    [
      jd, latexInput, personaIds, threadId, editedLatex,
      setStreaming, setCurrentNode, setLatexOutput, setPdfUrl,
      setCritique, setConsensus, setHitlPayload, setStoreError, onComplete,
    ]
  );

  const score = consensus?.consensus_score ?? null;
  const hasBlocking = (consensus?.blocking_issues ?? []).length > 0;
  const hasOptional = (consensus?.optional_improvements ?? []).length > 0;

  const scoreBand =
    score === null ? null
    : score >= 80 ? "green"
    : score >= 60 ? "yellow"
    : "red";

  // ── Edit mode ────────────────────────────────────────────────────────────────
  if (editMode) {
    return (
      <div className="border rounded-xl bg-white overflow-hidden shadow-sm">
        <div className="px-5 py-4 border-b bg-slate-50 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold">Edit LaTeX Source</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Make manual changes, then compile your version.
            </p>
          </div>
          <button
            onClick={() => { setEditMode(false); setEditedLatex(latex); }}
            disabled={submitting}
            className="text-xs text-muted-foreground hover:text-foreground px-3 py-1.5 rounded border hover:bg-muted/50 transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
        </div>

        <div className="p-4">
          <MonacoEditor value={editedLatex} onChange={setEditedLatex} readOnly={false} height="420px" />
        </div>

        {error && (
          <div className="px-5 py-2.5 text-sm text-red-600 bg-red-50 border-t">{error}</div>
        )}

        <div className="px-5 py-4 border-t">
          <button
            onClick={() => sendDecision("edit")}
            disabled={submitting}
            className="w-full py-3 text-sm font-semibold rounded-lg bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {submitting ? "Compiling…" : "Compile Edited LaTeX"}
          </button>
        </div>
      </div>
    );
  }

  // ── Review gate ───────────────────────────────────────────────────────────────
  return (
    <div className="border rounded-xl bg-white overflow-hidden shadow-sm">
      {/* Header */}
      <div className="px-5 py-4 border-b bg-gradient-to-r from-slate-50 to-blue-50/40">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse shrink-0" />
              <h3 className="text-sm font-semibold text-foreground">Human Review Gate</h3>
            </div>
            <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
              The AI pipeline has paused. Review the generated resume and choose what happens next.
            </p>
          </div>

          {score !== null && (
            <div
              className={cn(
                "shrink-0 px-3 py-2 rounded-lg border text-center min-w-[56px]",
                scoreBand === "green" && "bg-green-50 border-green-200",
                scoreBand === "yellow" && "bg-yellow-50 border-yellow-200",
                scoreBand === "red" && "bg-red-50 border-red-200",
              )}
            >
              <div
                className={cn(
                  "text-2xl font-bold leading-none tabular-nums",
                  scoreBand === "green" && "text-green-700",
                  scoreBand === "yellow" && "text-yellow-700",
                  scoreBand === "red" && "text-red-700",
                )}
              >
                {score}
              </div>
              <div className="text-[10px] text-muted-foreground mt-0.5 font-medium uppercase tracking-wide">
                score
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Issues */}
      {hasBlocking && (
        <div className="mx-5 mt-4 rounded-lg border border-red-200 bg-red-50 p-4">
          <p className="text-xs font-semibold text-red-700 uppercase tracking-wide mb-2">
            Blocking issues — approve will override
          </p>
          <ul className="space-y-1.5">
            {consensus!.blocking_issues.map((issue, i) => (
              <li key={i} className="flex gap-2 text-sm text-red-700">
                <span className="shrink-0 mt-px font-bold">✗</span>
                <span>{issue}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {hasOptional && (
        <div className="mx-5 mt-3 rounded-lg border border-yellow-200 bg-yellow-50 p-3.5">
          <p className="text-xs font-semibold text-yellow-700 uppercase tracking-wide mb-2">
            Optional improvements
          </p>
          <ul className="space-y-1">
            {consensus!.optional_improvements.map((imp, i) => (
              <li key={i} className="flex gap-2 text-sm text-yellow-800">
                <span className="shrink-0 mt-px">→</span>
                <span>{imp}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Decision cards */}
      <div className="p-5 space-y-3 pt-4">
        {/* Approve */}
        <button
          onClick={() => sendDecision("approve")}
          disabled={submitting}
          className={cn(
            "w-full flex items-start gap-4 p-4 rounded-xl border-2 text-left transition-all",
            "border-green-200 bg-green-50 hover:bg-green-100 hover:border-green-300",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            activeAction === "approve" && "ring-2 ring-green-400 ring-offset-1",
          )}
        >
          <div className="shrink-0 mt-0.5 w-9 h-9 rounded-full bg-green-600 text-white flex items-center justify-center text-lg font-bold">
            {activeAction === "approve" ? (
              <span className="block w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
            ) : (
              <span>✓</span>
            )}
          </div>
          <div>
            <div className="text-sm font-semibold text-green-900">Approve &amp; Compile</div>
            <div className="text-xs text-green-700 mt-0.5 leading-relaxed">
              Send the current resume to Tectonic for PDF compilation.
              {hasBlocking ? " Blocking issues above will be overridden." : " No blocking issues — good to go."}
            </div>
          </div>
        </button>

        {/* Regen */}
        <button
          onClick={() => sendDecision("regen")}
          disabled={submitting}
          className={cn(
            "w-full flex items-start gap-4 p-4 rounded-xl border-2 text-left transition-all",
            "border-blue-200 bg-blue-50 hover:bg-blue-100 hover:border-blue-300",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            activeAction === "regen" && "ring-2 ring-blue-400 ring-offset-1",
          )}
        >
          <div className="shrink-0 mt-0.5 w-9 h-9 rounded-full bg-blue-600 text-white flex items-center justify-center text-lg font-bold">
            {activeAction === "regen" ? (
              <span className="block w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
            ) : (
              <span>↺</span>
            )}
          </div>
          <div>
            <div className="text-sm font-semibold text-blue-900">Regenerate</div>
            <div className="text-xs text-blue-700 mt-0.5 leading-relaxed">
              Re-run the AI generator with the blocking issues above prepended as hard constraints.
            </div>
          </div>
        </button>

        {/* Edit */}
        <button
          onClick={() => setEditMode(true)}
          disabled={submitting}
          className={cn(
            "w-full flex items-start gap-4 p-4 rounded-xl border-2 text-left transition-all",
            "border-slate-200 bg-slate-50 hover:bg-slate-100 hover:border-slate-300",
            "disabled:opacity-50 disabled:cursor-not-allowed",
          )}
        >
          <div className="shrink-0 mt-0.5 w-9 h-9 rounded-full bg-slate-600 text-white flex items-center justify-center text-lg font-bold">
            ✎
          </div>
          <div>
            <div className="text-sm font-semibold text-slate-900">Edit LaTeX</div>
            <div className="text-xs text-slate-600 mt-0.5 leading-relaxed">
              Open the raw LaTeX source in an editor, make manual changes, then compile.
            </div>
          </div>
        </button>
      </div>

      {/* Collapsible LaTeX preview */}
      <div className="border-t">
        <button
          onClick={() => setShowLatex((v) => !v)}
          className="w-full px-5 py-2.5 text-xs text-muted-foreground hover:text-foreground flex items-center justify-between transition-colors hover:bg-muted/20"
        >
          <span>View generated LaTeX source</span>
          <span className="text-[10px]">{showLatex ? "▲ hide" : "▼ show"}</span>
        </button>
        {showLatex && (
          <div className="px-4 pb-4">
            <MonacoEditor value={latex} onChange={() => {}} readOnly height="360px" />
          </div>
        )}
      </div>

      {error && (
        <div className="px-5 py-3 text-sm text-red-600 bg-red-50 border-t">{error}</div>
      )}
    </div>
  );
}
