"use client";

/**
 * DebatePanel — shows per-persona critique cards + debate rounds + consensus.
 *
 * Sections:
 * 1. Per-persona critique (score, flags, suggestions, AI slop badge)
 * 2. Debate rounds (collapsible accordion per persona)
 * 3. DebateConsensus (blocking issues in red, optional improvements in yellow)
 */

import { useState } from "react";
import { cn } from "@/lib/utils";
import type { CritiqueResult, DebateConsensus, DebateRound } from "@/store/resumeStore";

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

function PersonaLabel({ id }: { id: string }) {
  return (
    <span className="font-mono text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 border">
      {id.replace(/_/g, " ")}
    </span>
  );
}

function CritiqueCard({ critique }: { critique: CritiqueResult }) {
  return (
    <div className="space-y-3 p-4 border-b last:border-b-0">
      <div className="flex items-center gap-3 flex-wrap">
        <PersonaLabel id={critique.persona_id} />
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
        <ul className="space-y-1">
          {critique.flags.map((flag, i) => (
            <li key={i} className="flex gap-2 text-sm text-red-600">
              <span className="shrink-0">⚠</span>
              <span>{flag}</span>
            </li>
          ))}
        </ul>
      )}

      {critique.suggestions.length > 0 && (
        <ul className="space-y-1">
          {critique.suggestions.map((s, i) => (
            <li key={i} className="flex gap-2 text-sm text-green-700">
              <span className="shrink-0">✓</span>
              <span>{s}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function DebateRoundAccordion({ round }: { round: DebateRound }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-2.5 text-sm font-medium bg-muted/30 hover:bg-muted/50 transition-colors"
      >
        <span className="flex items-center gap-2">
          <PersonaLabel id={round.persona_id} />
          <span className="text-xs text-muted-foreground">responding to {round.response_to.join(", ")}</span>
        </span>
        <span className="text-muted-foreground">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <ul className="p-4 space-y-1.5 bg-white">
          {round.key_points.map((pt, i) => (
            <li key={i} className="text-sm text-foreground">
              • {pt}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ConsensusSection({ consensus }: { consensus: DebateConsensus }) {
  return (
    <div className="space-y-4 p-4 border rounded-lg bg-white">
      <div className="flex items-center gap-3">
        <ScoreBadge score={consensus.consensus_score} />
        <span className="text-sm font-medium">Debate Consensus</span>
      </div>

      {consensus.blocking_issues.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-red-600 uppercase tracking-wide mb-2">
            Must Fix Before Compile
          </p>
          <ul className="space-y-1.5">
            {consensus.blocking_issues.map((issue, i) => (
              <li key={i} className="flex gap-2 text-sm text-red-700 bg-red-50 rounded px-3 py-1.5">
                <span className="shrink-0">🚫</span>
                <span>{issue}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {consensus.optional_improvements.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-yellow-700 uppercase tracking-wide mb-2">
            Optional Improvements
          </p>
          <ul className="space-y-1.5">
            {consensus.optional_improvements.map((imp, i) => (
              <li key={i} className="flex gap-2 text-sm text-yellow-800 bg-yellow-50 rounded px-3 py-1.5">
                <span className="shrink-0">💡</span>
                <span>{imp}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────

interface DebatePanelProps {
  critique: CritiqueResult[];
  consensus: DebateConsensus | null;
}

export function DebatePanel({ critique, consensus }: DebatePanelProps) {
  if (!critique.length && !consensus) return null;

  const rounds = consensus?.debate_rounds ?? [];

  return (
    <div className="space-y-6">
      {/* Per-persona critiques */}
      {critique.length > 0 && (
        <div className="border rounded-lg overflow-hidden bg-white">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground px-4 py-2.5 border-b bg-muted/30">
            Persona Critiques
          </h3>
          {critique.map((c) => (
            <CritiqueCard key={c.persona_id} critique={c} />
          ))}
        </div>
      )}

      {/* Debate rounds */}
      {rounds.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Debate Rounds
          </h3>
          {rounds.map((r, i) => (
            <DebateRoundAccordion key={i} round={r} />
          ))}
        </div>
      )}

      {/* Consensus */}
      {consensus && <ConsensusSection consensus={consensus} />}
    </div>
  );
}
