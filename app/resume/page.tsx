"use client";

/**
 * app/resume/page.tsx — Main resume editor + preview page.
 *
 * Two-column layout:
 *   Left  (sticky): DensityMeter + ResumePreview (A4 locked) + ExportButton
 *   Right (scrollable): pipeline progress + CritiquePanel + IterationInput + history
 *
 * This page is client-only because react-pdf's PDFViewer requires browser APIs.
 */

import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useResumeStore } from "@/store/resumeStore";
import { DensityMeter } from "@/components/DensityMeter";
import { CritiquePanel } from "@/components/CritiquePanel";
import { IterationInput } from "@/components/IterationInput";
import { ExportButton } from "@/components/ExportButton";

// PDFViewer is SSR-incompatible — load client-side only
const ResumePreview = dynamic(
  () => import("@/components/ResumePreview").then((m) => m.ResumePreview),
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center h-[700px] border rounded-lg bg-muted/20">
        <span className="text-sm text-muted-foreground">Loading preview…</span>
      </div>
    ),
  }
);

// Node progress labels
const NODE_LABELS: Record<string, string> = {
  ingest: "Parsing inputs",
  compress: "Compressing JD",
  embed_and_cache: "Checking cache",
  generate: "Generating resume",
  critique: "Running critique (×3 parallel)",
  resolve: "Synthesising feedback",
  iterate: "Preparing next iteration",
};

export default function ResumePage() {
  const router = useRouter();
  const draft = useResumeStore((s) => s.draft);
  const critique = useResumeStore((s) => s.critique);
  const isStreaming = useResumeStore((s) => s.isStreaming);
  const currentNode = useResumeStore((s) => s.currentNode);
  const error = useResumeStore((s) => s.error);
  const history = useResumeStore((s) => s.history);

  // Redirect to landing if there's no data to show
  if (!draft && !isStreaming) {
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

          {/* Pipeline progress badge */}
          {isStreaming && currentNode && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className="animate-spin h-3.5 w-3.5 border-2 border-primary border-t-transparent rounded-full" />
              <span>{NODE_LABELS[currentNode] ?? currentNode}</span>
            </div>
          )}

          {draft && !isStreaming && (
            <span className="text-xs text-green-600 font-medium">
              ✓ Ready
            </span>
          )}
        </div>
      </nav>

      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">

          {/* ── Left column: Resume preview ─────────────────────────────── */}
          <div className="space-y-4 lg:sticky lg:top-20">
            <DensityMeter />
            <ResumePreview />
            <ExportButton />
          </div>

          {/* ── Right column: Critique + iteration ──────────────────────── */}
          <div className="space-y-6">
            {/* Error banner */}
            {error && (
              <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
                <strong>Error:</strong> {error}
              </div>
            )}

            {/* Critique panel */}
            {critique.length > 0 && (
              <div className="space-y-2">
                <h2 className="text-sm font-semibold text-foreground">
                  AI Critique
                </h2>
                <CritiquePanel />
              </div>
            )}

            {/* Streaming placeholder for critique */}
            {isStreaming && currentNode === "critique" && !critique.length && (
              <div className="border rounded-lg p-6 text-center space-y-2 text-muted-foreground bg-white">
                <div className="animate-spin h-5 w-5 border-2 border-primary border-t-transparent rounded-full mx-auto" />
                <p className="text-sm">
                  Running recruiter, hiring manager & expert critique in parallel…
                </p>
              </div>
            )}

            {/* Iteration input */}
            {draft && (
              <div className="bg-white border rounded-lg p-4 space-y-3">
                <div>
                  <h2 className="text-sm font-semibold text-foreground">
                    Refine with Feedback
                  </h2>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Tell the AI what to change. Up to 3 iterations total.
                  </p>
                </div>
                <IterationInput />
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
                      <span>
                        {h.word_count} words · ATS {h.ats_score_estimate}/100
                      </span>
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
