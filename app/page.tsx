"use client";

/**
 * app/page.tsx — Landing page.
 *
 * Users provide:
 * 1. Job description (required) — plain textarea
 * 2. LaTeX resume (required) — Monaco editor with syntax highlighting
 * 3. Persona selection (required) — multi-select checkboxes
 *
 * On submit:
 * - Calls POST /api/generate (SSE stream)
 * - Parses events to update Zustand state
 * - Redirects to /resume once HITL interrupt fires (human_review_node)
 *   or immediately on cache hit (pdf_url returned)
 */

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useResumeStore } from "@/store/resumeStore";
import type { LaTeXOutput, CritiqueResult, DebateConsensus, HITLPayload } from "@/store/resumeStore";
import dynamic from "next/dynamic";

// Monaco must be loaded client-side only
const MonacoEditor = dynamic(
  () => import("@/components/MonacoEditor").then((m) => m.MonacoEditor),
  { ssr: false }
);

const AVAILABLE_PERSONAS = [
  { id: "faang_bar_raiser", label: "FAANG Bar Raiser" },
  { id: "principal_engineer", label: "Principal Engineer" },
  { id: "startup_cto", label: "Startup CTO" },
  { id: "ai_ml_researcher", label: "AI/ML Researcher" },
  { id: "ats_recruiter", label: "ATS Recruiter" },
];

const NODE_LABELS: Record<string, string> = {
  ingest_node: "Parsing inputs…",
  embed_and_cache_node: "Checking semantic cache…",
  analyze_latex_node: "Analysing LaTeX structure…",
  generate_node: "Generating tailored resume…",
  critique_persona: "Running persona critiques…",
  debate_node: "Running debate…",
  human_review_node: "Waiting for human review…",
  compile_node: "Compiling PDF…",
  compress_latex_node: "Compressing LaTeX…",
  cache_and_store_node: "Caching result…",
};

export default function LandingPage() {
  const [jd, setJd] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  const router = useRouter();

  const {
    latexInput,
    setLatexInput,
    personaIds,
    setPersonaIds,
    setJd: setStoreJd,
    setThreadId,
    setStreaming,
    setCurrentNode,
    setLatexOutput,
    setPdfUrl,
    setCritique,
    setConsensus,
    setHitlPayload,
    setError,
    isStreaming,
    currentNode,
    reset,
  } = useResumeStore();

  const togglePersona = useCallback(
    (id: string) => {
      setPersonaIds(
        personaIds.includes(id)
          ? personaIds.filter((p) => p !== id)
          : [...personaIds, id]
      );
    },
    [personaIds, setPersonaIds]
  );

  const handleSubmit = useCallback(async () => {
    if (!jd.trim()) {
      setLocalError("Please paste a job description.");
      return;
    }
    if (!latexInput.trim() || !latexInput.includes("\\begin{document}")) {
      setLocalError("Please provide a valid LaTeX resume containing \\begin{document}.");
      return;
    }
    if (personaIds.length === 0) {
      setLocalError("Please select at least one persona.");
      return;
    }

    setLocalError(null);
    reset();
    setStoreJd(jd);
    setStreaming(true);
    setCurrentNode("ingest_node");

    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          jd_raw: jd,
          latex_input: latexInput,
          selected_persona_ids: personaIds,
        }),
      });

      if (!res.ok || !res.body) {
        throw new Error(`Pipeline error: ${res.status}`);
      }

      const threadId = res.headers.get("X-Thread-ID") ?? "";
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
                latex_output?: LaTeXOutput;
                pdf_url?: string;
                critique_results?: CritiqueResult[];
                consensus?: DebateConsensus;
                hitl?: HITLPayload;
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

            // HITL interrupt — redirect to review page
            if (event.node === "human_review_node" && event.state?.hitl) {
              setHitlPayload(event.state.hitl);
              router.push("/resume");
              return;
            }

            // Cache hit — pdf ready immediately
            if (event.state?.pdf_url) {
              router.push("/resume");
              return;
            }
          } catch {
            // Skip malformed SSE lines
          }
        }
      }
    } catch (err) {
      setError(String(err));
      setLocalError(String(err));
    } finally {
      setStreaming(false);
      setCurrentNode(null);
    }
  }, [
    jd, latexInput, personaIds,
    reset, setStoreJd,
    setThreadId, setStreaming, setCurrentNode,
    setLatexOutput, setPdfUrl, setCritique,
    setConsensus, setHitlPayload, setError, router,
  ]);

  const progressLabel = currentNode ? (NODE_LABELS[currentNode] ?? `${currentNode}…`) : null;

  return (
    <main className="min-h-screen bg-gradient-to-b from-slate-50 to-white">
      <div className="max-w-4xl mx-auto py-16 px-4 space-y-8">
        {/* Header */}
        <div className="text-center space-y-3">
          <h1 className="text-4xl font-bold tracking-tight text-foreground">
            Resume Optimizer
          </h1>
          <p className="text-lg text-muted-foreground max-w-xl mx-auto">
            Paste a job description, provide your LaTeX resume, and get a
            single-page ATS-optimized PDF with multi-persona AI critique.
          </p>
        </div>

        {/* Feature badges */}
        <div className="flex flex-wrap justify-center gap-2 text-xs">
          {[
            "LaTeX in / PDF out",
            "Single-page A4 guarantee",
            "Multi-persona debate",
            "Human-in-the-loop review",
            "Semantic cache (instant on repeat JDs)",
          ].map((f) => (
            <span key={f} className="px-3 py-1 rounded-full border bg-white text-muted-foreground">
              {f}
            </span>
          ))}
        </div>

        {/* Form */}
        <div className="space-y-6">
          {/* Job Description */}
          <div className="space-y-1.5">
            <label htmlFor="jd-input" className="text-sm font-medium text-foreground">
              Job Description <span className="text-red-500">*</span>
            </label>
            <textarea
              id="jd-input"
              className="w-full min-h-[180px] p-3 text-sm border rounded-lg bg-background resize-y focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
              placeholder="Paste the full job description here…"
              value={jd}
              onChange={(e) => setJd(e.target.value)}
              disabled={isStreaming}
              rows={8}
            />
          </div>

          {/* LaTeX Resume */}
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-foreground">
              Your LaTeX Resume <span className="text-red-500">*</span>
            </label>
            <p className="text-xs text-muted-foreground">
              Must be a complete LaTeX document with <code className="font-mono bg-muted px-1 rounded">\begin{"{"+"document"+"}"}</code>.
            </p>
            <div className={isStreaming ? "opacity-50 pointer-events-none" : ""}>
              <MonacoEditor
                value={latexInput}
                onChange={setLatexInput}
                readOnly={isStreaming}
                height="350px"
              />
            </div>
          </div>

          {/* Persona selection */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">
              Critique Personas <span className="text-red-500">*</span>
            </label>
            <p className="text-xs text-muted-foreground">Select at least one persona to review your resume.</p>
            <div className="flex flex-wrap gap-2">
              {AVAILABLE_PERSONAS.map(({ id, label }) => {
                const selected = personaIds.includes(id);
                return (
                  <button
                    key={id}
                    type="button"
                    onClick={() => togglePersona(id)}
                    disabled={isStreaming}
                    className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors disabled:opacity-50 ${
                      selected
                        ? "bg-primary text-primary-foreground border-primary"
                        : "bg-white text-foreground border-border hover:bg-muted/50"
                    }`}
                  >
                    {selected ? "✓ " : ""}{label}
                  </button>
                );
              })}
            </div>
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
