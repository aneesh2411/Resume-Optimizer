"use client";

/**
 * CritiquePanel — per-persona critique display.
 *
 * Shows a tab per persona (dynamic persona_id) + a Consensus tab.
 * Each tab displays: score, JD match confidence, flags, suggestions, AI slop badge.
 */

import { useState } from "react";
import { useResumeStore, type CritiqueResult, type DebateConsensus } from "@/store/resumeStore";
import { cn } from "@/lib/utils";

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

      {critique.flags.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Issues Found</p>
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

      {critique.suggestions.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Suggestions</p>
          <ul className="space-y-1.5">
            {critique.suggestions.map((s, i) => (
              <li key={i} className="flex gap-2 text-sm text-green-700">
                <span className="mt-0.5 shrink-0">✓</span>
                <span>{s}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function ConsensusCard({ consensus }: { consensus: DebateConsensus }) {
  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center gap-3">
        <ScoreBadge score={consensus.consensus_score} />
        <span className="text-sm text-muted-foreground">Consensus Score</span>
      </div>

      {consensus.blocking_issues.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-red-600 uppercase tracking-wide mb-2">Must Fix Before Compile</p>
          <ul className="space-y-1.5">
            {consensus.blocking_issues.map((issue, i) => (
              <li key={i} className="flex gap-2 text-sm text-red-700">
                <span className="mt-0.5 shrink-0">🚫</span>
                <span>{issue}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {consensus.optional_improvements.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-yellow-700 uppercase tracking-wide mb-2">Optional Improvements</p>
          <ul className="space-y-1.5">
            {consensus.optional_improvements.map((imp, i) => (
              <li key={i} className="flex gap-2 text-sm text-yellow-800">
                <span className="mt-0.5 shrink-0">💡</span>
                <span>{imp}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function CritiquePanel() {
  const critique = useResumeStore((s) => s.critique);
  const consensus = useResumeStore((s) => s.consensus);
  const isStreaming = useResumeStore((s) => s.isStreaming);
  const currentNode = useResumeStore((s) => s.currentNode);
  const [activeTab, setActiveTab] = useState<string | null>(null);

  if (isStreaming && currentNode === "critique_persona") {
    return (
      <div className="border rounded-lg p-6 text-center space-y-2 text-muted-foreground">
        <div className="animate-spin h-5 w-5 border-2 border-primary border-t-transparent rounded-full mx-auto" />
        <p className="text-sm">Running multi-persona critique in parallel…</p>
      </div>
    );
  }

  if (!critique.length && !consensus) return null;

  const tabs = critique.map((c) => c.persona_id);
  if (consensus) tabs.push("consensus");
  const currentTab = activeTab ?? tabs[0] ?? null;

  return (
    <div className="border rounded-lg overflow-hidden">
      <div className="flex border-b bg-muted/30 overflow-x-auto">
        {tabs.map((tab) => {
          const c = tab === "consensus" ? null : critique.find((x) => x.persona_id === tab);
          const score = c ? ` (${c.score})` : consensus ? ` (${consensus.consensus_score})` : "";
          return (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={cn(
                "flex-shrink-0 py-2.5 px-3 text-xs font-medium text-center border-r last:border-r-0 hover:bg-muted/50 transition-colors whitespace-nowrap",
                currentTab === tab && "bg-background font-semibold"
              )}
            >
              {tab.replace(/_/g, " ")}{score}
            </button>
          );
        })}
      </div>

      {currentTab !== "consensus" &&
        critique.find((c) => c.persona_id === currentTab) && (
          <CritiqueCard critique={critique.find((c) => c.persona_id === currentTab)!} />
        )}

      {currentTab === "consensus" && consensus && (
        <ConsensusCard consensus={consensus} />
      )}
    </div>
  );
}
