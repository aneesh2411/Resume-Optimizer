"use client";

/**
 * CritiquePanel — tabbed multi-persona critique display.
 *
 * Shows three tabs: Recruiter / Hiring Manager / Expert.
 * Each tab displays: score, JD match confidence, flags, suggestions, AI slop badge.
 * A fourth "Consensus" tab shows the ConflictResolution with blocking issues.
 *
 * Uses shadcn/ui Tabs (installed separately via CLI).
 */

import { useResumeStore, type CritiqueResult, type ConflictResolution } from "@/store/resumeStore";
import { cn } from "@/lib/utils";

// ── Sub-components ────────────────────────────────────────────────────────────

function ScoreBadge({ score }: { score: number }) {
  const colour =
    score >= 80 ? "text-green-700 bg-green-50 border-green-200"
    : score >= 60 ? "text-yellow-700 bg-yellow-50 border-yellow-200"
    : "text-red-700 bg-red-50 border-red-200";

  return (
    <span className={cn("inline-flex items-baseline gap-0.5 text-xl font-bold px-2 py-0.5 rounded border", colour)}>
      {score}
      <span className="text-xs font-normal">/100</span>
    </span>
  );
}

function CritiqueCard({ critique }: { critique: CritiqueResult }) {
  return (
    <div className="space-y-4 p-4">
      {/* Score row */}
      <div className="flex items-center gap-3 flex-wrap">
        <ScoreBadge score={critique.score} />
        <span className="text-sm text-muted-foreground">
          JD Match: <strong>{critique.jd_match_confidence}%</strong>
        </span>
        {critique.ai_slop_detected && (
          <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-700 border border-red-200 font-medium">
            AI Slop Detected
          </span>
        )}
      </div>

      {/* Flags */}
      {critique.flags.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
            Issues Found
          </p>
          <ul className="space-y-1.5">
            {critique.flags.map((flag, i) => (
              <li key={i} className="flex gap-2 text-sm text-red-600">
                <span className="mt-0.5 shrink-0">⚠</span>
                <span>{flag}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Suggestions */}
      {critique.suggestions.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
            Suggestions
          </p>
          <ul className="space-y-1.5">
            {critique.suggestions.map((suggestion, i) => (
              <li key={i} className="flex gap-2 text-sm text-green-700">
                <span className="mt-0.5 shrink-0">✓</span>
                <span>{suggestion}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function ConsensusCard({ resolution }: { resolution: ConflictResolution }) {
  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center gap-3">
        <ScoreBadge score={resolution.consensus_score} />
        <span className="text-sm text-muted-foreground">Consensus Score</span>
      </div>

      {resolution.blocking_issues.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-red-600 uppercase tracking-wide mb-2">
            Must Fix Before Export
          </p>
          <ul className="space-y-1.5">
            {resolution.blocking_issues.map((issue, i) => (
              <li key={i} className="flex gap-2 text-sm text-red-700">
                <span className="mt-0.5 shrink-0">🚫</span>
                <span>{issue}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {resolution.optional_improvements.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-green-700 uppercase tracking-wide mb-2">
            Optional Improvements
          </p>
          <ul className="space-y-1.5">
            {resolution.optional_improvements.map((improvement, i) => (
              <li key={i} className="flex gap-2 text-sm text-green-700">
                <span className="mt-0.5 shrink-0">✓</span>
                <span>{improvement}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {resolution.priority_flags.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
            All Priority Flags (ranked)
          </p>
          <ol className="space-y-1 list-decimal list-inside">
            {resolution.priority_flags.map((flag, i) => (
              <li key={i} className="text-sm text-foreground">
                {flag}
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

type TabKey = "recruiter" | "hiring_manager" | "expert" | "consensus";

const TAB_LABELS: Record<TabKey, string> = {
  recruiter: "Recruiter",
  hiring_manager: "Hiring Manager",
  expert: "Expert",
  consensus: "Consensus",
};

export function CritiquePanel() {
  const critique = useResumeStore((s) => s.critique);
  const resolution = useResumeStore((s) => s.resolution);
  const isStreaming = useResumeStore((s) => s.isStreaming);
  const currentNode = useResumeStore((s) => s.currentNode);

  if (isStreaming && currentNode === "critique") {
    return (
      <div className="border rounded-lg p-6 text-center space-y-2 text-muted-foreground">
        <div className="animate-spin h-5 w-5 border-2 border-primary border-t-transparent rounded-full mx-auto" />
        <p className="text-sm">Running multi-persona critique in parallel…</p>
      </div>
    );
  }

  if (!critique.length) {
    return null;
  }

  const recruiter = critique.find((c) => c.role === "recruiter");
  const hm = critique.find((c) => c.role === "hiring_manager");
  const expert = critique.find((c) => c.role === "expert");

  const tabs: TabKey[] = ["recruiter", "hiring_manager", "expert"];
  if (resolution) tabs.push("consensus");

  // Simple tab implementation (no shadcn dependency at this stage)
  // Will be replaced with shadcn Tabs after installation
  return (
    <div className="border rounded-lg overflow-hidden">
      <div className="flex border-b bg-muted/30">
        {tabs.map((tab) => {
          const c = tab === "consensus" ? null : critique.find((x) => x.role === tab);
          const score = c ? ` (${c.score})` : resolution ? ` (${resolution.consensus_score})` : "";
          return (
            <button
              key={tab}
              className="flex-1 py-2.5 text-xs font-medium text-center border-r last:border-r-0 hover:bg-muted/50 transition-colors"
              data-tab={tab}
              onClick={(e) => {
                const parent = e.currentTarget.closest(".border.rounded-lg");
                if (!parent) return;
                parent.querySelectorAll("[data-tab-panel]").forEach((el) => {
                  (el as HTMLElement).style.display = "none";
                });
                parent.querySelector(`[data-tab-panel="${tab}"]`)?.removeAttribute("style");
                parent.querySelectorAll("[data-tab]").forEach((el) => {
                  el.classList.remove("bg-background", "font-semibold");
                });
                e.currentTarget.classList.add("bg-background", "font-semibold");
              }}
            >
              {TAB_LABELS[tab]}
              {score}
            </button>
          );
        })}
      </div>

      {/* Recruiter panel */}
      <div data-tab-panel="recruiter">
        {recruiter && <CritiqueCard critique={recruiter} />}
      </div>

      {/* Hiring Manager panel */}
      <div data-tab-panel="hiring_manager" style={{ display: "none" }}>
        {hm && <CritiqueCard critique={hm} />}
      </div>

      {/* Expert panel */}
      <div data-tab-panel="expert" style={{ display: "none" }}>
        {expert && <CritiqueCard critique={expert} />}
      </div>

      {/* Consensus panel */}
      {resolution && (
        <div data-tab-panel="consensus" style={{ display: "none" }}>
          <ConsensusCard resolution={resolution} />
        </div>
      )}
    </div>
  );
}
