"use client";

/**
 * app/resume/page.tsx — Resume review + output page.
 *
 * Two-column layout:
 *   Left  (sticky): DensityMeter + PDFViewer (post-compile) or LaTeX diff + ExportButton
 *   Right (scrollable): progress + DebatePanel + HITLPanel (when interrupted) + history
 */

import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useResumeStore } from "@/store/resumeStore";
import { DensityMeter } from "@/components/DensityMeter";
import { ExportButton } from "@/components/ExportButton";
import { DebatePanel } from "@/components/DebatePanel";
import { DiffViewer } from "@/components/DiffViewer";

// SSR-incompatible components — load client-side only
const PDFViewer = dynamic(
  () => import("@/components/PDFViewer").then((m) => m.PDFViewer),
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center h-[700px] border rounded-lg bg-muted/20">
        <span className="text-sm text-muted-foreground">Loading PDF…</span>
      </div>
    ),
  }
);

const HITLPanel = dynamic(
  () => import("@/components/HITLPanel").then((m) => m.HITLPanel),
  { ssr: false }
);

const NODE_LABELS: Record<string, string> = {
  ingest_node: "Parsing inputs",
  embed_and_cache_node: "Checking cache",
  analyze_latex_node: "Analysing LaTeX",
  generate_node: "Generating resume",
  critique_persona: "Running critique",
  debate_node: "Running debate",
  human_review_node: "Awaiting review",
  compile_node: "Compiling PDF",
  compress_latex_node: "Compressing LaTeX",
  cache_and_store_node: "Caching result",
};

export default function ResumePage() {
  const router = useRouter();
  const latexOutput = useResumeStore((s) => s.latexOutput);
  const latexInput = useResumeStore((s) => s.latexInput);
  const pdfUrl = useResumeStore((s) => s.pdfUrl);
  const critique = useResumeStore((s) => s.critique);
  const consensus = useResumeStore((s) => s.consensus);
  const hitlPayload = useResumeStore((s) => s.hitlPayload);
  const threadId = useResumeStore((s) => s.threadId);
  const isStreaming = useResumeStore((s) => s.isStreaming);
  const currentNode = useResumeStore((s) => s.currentNode);
  const error = useResumeStore((s) => s.error);
  const history = useResumeStore((s) => s.history);
  const setHitlPayload = useResumeStore((s) => s.setHitlPayload);


  if (!latexOutput && !hitlPayload && !pdfUrl && !isStreaming) {
    return (
      <div className="min-h-screen flex items-center justify-center flex-col gap-4">
        <p className="text-muted-foreground">No resume data found.</p>
        <button
          onClick={() => router.push("/")}
          className="text-sm text-primary underline"
        >
          Go back to the optimizer
        </button>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Navbar */}
      <nav className="sticky top-0 z-10 border-b bg-white/80 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <button
            onClick={() => router.push("/")}
            className="text-sm font-semibold text-foreground hover:text-primary transition-colors"
          >
            ← Resume Optimizer
          </button>

          {isStreaming && currentNode && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className="animate-spin h-3.5 w-3.5 border-2 border-primary border-t-transparent rounded-full" />
              <span>{NODE_LABELS[currentNode] ?? currentNode}</span>
            </div>
          )}

          {pdfUrl && !isStreaming && (
            <span className="text-xs text-green-600 font-medium">✓ PDF Ready</span>
          )}

          {hitlPayload && !pdfUrl && (
            <span className="text-xs text-blue-600 font-medium">Review Required</span>
          )}
        </div>
      </nav>

      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">

          {/* ── Left column: Preview ─────────────────────────────────────── */}
          <div className="space-y-4 lg:sticky lg:top-20">
            {latexOutput && <DensityMeter />}

            {pdfUrl ? (
              <PDFViewer url={pdfUrl} />
            ) : latexOutput ? (
              <DiffViewer original={latexInput} modified={latexOutput.full_latex} />
            ) : null}

            <ExportButton />
          </div>

          {/* ── Right column: Review + critique ─────────────────────────── */}
          <div className="space-y-6">
            {error && (
              <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
                <strong>Error:</strong> {error}
              </div>
            )}

            {/* HITL panel — shown when graph is paused at human_review_node */}
            {hitlPayload && threadId && !pdfUrl && (
              <HITLPanel
                latex={hitlPayload.latex ?? latexOutput?.full_latex ?? ""}
                consensus={hitlPayload.consensus}
                critique={hitlPayload.critique_results}
                threadId={threadId}
                onComplete={() => {
                  setHitlPayload(null);
                  // pdfUrl will be set via SSE in HITLPanel
                }}
              />
            )}

            {/* Debate panel */}
            {(critique.length > 0 || consensus) && (
              <DebatePanel critique={critique} consensus={consensus} />
            )}

            {/* Streaming placeholders */}
            {isStreaming && currentNode === "critique_persona" && !critique.length && (
              <div className="border rounded-lg p-6 text-center space-y-2 text-muted-foreground bg-white">
                <div className="animate-spin h-5 w-5 border-2 border-primary border-t-transparent rounded-full mx-auto" />
                <p className="text-sm">Running persona critiques in parallel…</p>
              </div>
            )}

            {isStreaming && currentNode === "debate_node" && (
              <div className="border rounded-lg p-6 text-center space-y-2 text-muted-foreground bg-white">
                <div className="animate-spin h-5 w-5 border-2 border-primary border-t-transparent rounded-full mx-auto" />
                <p className="text-sm">Running debate round…</p>
              </div>
            )}

            {isStreaming && currentNode === "compile_node" && (
              <div className="border rounded-lg p-6 text-center space-y-2 text-muted-foreground bg-white">
                <div className="animate-spin h-5 w-5 border-2 border-primary border-t-transparent rounded-full mx-auto" />
                <p className="text-sm">Compiling LaTeX to PDF…</p>
              </div>
            )}

            {/* Iteration history */}
            {history.length > 0 && (
              <div className="space-y-2">
                <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                  Previous Iterations ({history.length})
                </h2>
                <div className="space-y-1.5">
                  {history.map((h, i) => (
                    <div
                      key={i}
                      className="text-xs border rounded-lg px-3 py-2 bg-white text-muted-foreground flex justify-between"
                    >
                      <span>Iteration {i + 1}</span>
                      <span>{h.word_count} words · ATS {h.ats_score_estimate}/100</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
