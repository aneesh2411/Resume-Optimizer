"use client";

/**
 * app/resume/[id]/critique/page.tsx — Session-specific critique view.
 *
 * Allows deep-linking to a specific critique session via its thread_id.
 * The page loads session state from Zustand (persisted in localStorage).
 * If the session is not found locally, it shows a "session expired" message.
 */

import { useParams, useRouter } from "next/navigation";
import { useResumeStore } from "@/store/resumeStore";
import { CritiquePanel } from "@/components/CritiquePanel";
import { ExportButton } from "@/components/ExportButton";

export default function CritiquePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();

  const threadId = useResumeStore((s) => s.threadId);
  const critique = useResumeStore((s) => s.critique);
  const resolution = useResumeStore((s) => s.resolution);
  const draft = useResumeStore((s) => s.draft);

  const sessionMatch = threadId === params.id;

  if (!sessionMatch || !critique.length) {
    return (
      <div className="min-h-screen flex items-center justify-center flex-col gap-4 px-4">
        <div className="text-center space-y-3 max-w-sm">
          <h1 className="text-xl font-semibold">Critique Not Found</h1>
          <p className="text-sm text-muted-foreground">
            This critique session has expired or belongs to a different browser session.
          </p>
          <button
            onClick={() => router.push("/")}
            className="inline-block px-4 py-2 text-sm font-medium rounded-lg bg-primary text-primary-foreground"
          >
            Start a new resume
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <nav className="sticky top-0 z-10 border-b bg-white/80 backdrop-blur-sm">
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center justify-between">
          <button
            onClick={() => router.back()}
            className="text-sm font-medium text-foreground hover:text-primary"
          >
            ← Back to Resume
          </button>
          <span className="text-xs text-muted-foreground">
            Session: {params.id.slice(0, 8)}…
          </span>
        </div>
      </nav>

      <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
        <div>
          <h1 className="text-2xl font-bold">AI Critique Report</h1>
          {draft && (
            <p className="text-sm text-muted-foreground mt-1">
              ATS Score: {draft.ats_score_estimate}/100 · {draft.word_count} words ·
              Format: {draft.format_used}
            </p>
          )}
        </div>

        <CritiquePanel />

        {resolution && (
          <div className="rounded-lg border bg-white p-4 space-y-2">
            <h2 className="text-sm font-semibold">Consensus Summary</h2>
            <p className="text-sm text-muted-foreground">
              Overall consensus score: <strong>{resolution.consensus_score}/100</strong>
            </p>
            {resolution.blocking_issues.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-red-600 uppercase tracking-wide mt-3 mb-1">
                  Must fix before export
                </p>
                <ul className="space-y-1">
                  {resolution.blocking_issues.map((issue, i) => (
                    <li key={i} className="text-sm text-red-700">
                      🚫 {issue}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        <ExportButton />
      </div>
    </div>
  );
}
