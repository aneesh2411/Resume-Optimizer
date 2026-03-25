/**
 * store/resumeStore.ts — Zustand global state for the resume optimizer.
 *
 * State domains:
 * - Session: threadId, latexInput, jd, personaIds
 * - Pipeline: isStreaming, currentNode, error
 * - Data: latexOutput, pdfUrl, critique, consensus, hitlPayload, history
 *
 * Persisted to localStorage: threadId + history (lightweight)
 * Not persisted: latexOutput, critique, consensus, hitlPayload (re-fetched on restore)
 */

"use client";

import { create } from "zustand";
import { devtools, persist } from "zustand/middleware";

// ── Type mirrors of the Python Pydantic schemas ───────────────────────────────

export interface LaTeXSection {
  name: string;
  content: string;
}

export interface LaTeXOutput {
  full_latex: string;
  sections: LaTeXSection[];
  format_used: "STAR" | "XYZ" | "CAR";
  ats_score_estimate: number;
  word_count: number;
}

export interface LaTeXAnalysis {
  total_bullets: number;
  avg_bullet_words: number;
  section_count: number;
  total_words: number;
  sections: string[];
  keyword_gaps: string[];
}

export interface CritiqueResult {
  persona_id: string;
  score: number;
  flags: string[];
  suggestions: string[];
  ai_slop_detected: boolean;
  jd_match_confidence: number;
}

export interface DebateRound {
  persona_id: string;
  response_to: string[];
  key_points: string[];
}

export interface DebateConsensus {
  blocking_issues: string[];
  optional_improvements: string[];
  consensus_score: number;
  debate_rounds: DebateRound[];
}

/** Payload surfaced by human_review_node interrupt() — shown in HITLPanel */
export interface HITLPayload {
  latex: string | null;
  consensus: DebateConsensus | null;
  critique_results: CritiqueResult[];
}

// ── Store interface ───────────────────────────────────────────────────────────

interface ResumeState {
  // Session
  threadId: string | null;
  jd: string;
  latexInput: string;
  personaIds: string[];

  // Pipeline progress
  isStreaming: boolean;
  currentNode: string | null;
  error: string | null;

  // Resume data
  latexOutput: LaTeXOutput | null;
  pdfUrl: string | null;
  critique: CritiqueResult[];
  consensus: DebateConsensus | null;
  hitlPayload: HITLPayload | null;
  history: LaTeXOutput[]; // previous generation drafts

  // ── Actions ──────────────────────────────────────────────────────────────

  setJd: (jd: string) => void;
  setLatexInput: (latex: string) => void;
  setPersonaIds: (ids: string[]) => void;
  setThreadId: (id: string) => void;

  setStreaming: (streaming: boolean) => void;
  setCurrentNode: (node: string | null) => void;
  setError: (error: string | null) => void;

  /** Set a new latex output. Automatically pushes the previous one to history. */
  setLatexOutput: (output: LaTeXOutput) => void;
  setPdfUrl: (url: string | null) => void;
  setCritique: (critique: CritiqueResult[]) => void;
  setConsensus: (consensus: DebateConsensus) => void;
  setHitlPayload: (payload: HITLPayload | null) => void;

  reset: () => void;
}

// ── Initial state ─────────────────────────────────────────────────────────────

const initialState: Omit<
  ResumeState,
  | "setJd"
  | "setLatexInput"
  | "setPersonaIds"
  | "setThreadId"
  | "setStreaming"
  | "setCurrentNode"
  | "setError"
  | "setLatexOutput"
  | "setPdfUrl"
  | "setCritique"
  | "setConsensus"
  | "setHitlPayload"
  | "reset"
> = {
  threadId: null,
  jd: "",
  latexInput: "",
  personaIds: [],
  isStreaming: false,
  currentNode: null,
  error: null,
  latexOutput: null,
  pdfUrl: null,
  critique: [],
  consensus: null,
  hitlPayload: null,
  history: [],
};

// ── Store ──────────────────────────────────────────────────────────────────────

export const useResumeStore = create<ResumeState>()(
  devtools(
    persist(
      (set, get) => ({
        ...initialState,

        setJd: (jd) => set({ jd }),
        setLatexInput: (latex) => set({ latexInput: latex }),
        setPersonaIds: (ids) => set({ personaIds: ids }),
        setThreadId: (id) => set({ threadId: id }),

        setStreaming: (streaming) => set({ isStreaming: streaming }),
        setCurrentNode: (node) => set({ currentNode: node }),
        setError: (error) => set({ error }),

        setLatexOutput: (output) => {
          const previous = get().latexOutput;
          const history = previous
            ? [...get().history, previous]
            : get().history;
          set({ latexOutput: output, history });
        },

        setPdfUrl: (url) => set({ pdfUrl: url }),
        setCritique: (critique) => set({ critique }),
        setConsensus: (consensus) => set({ consensus }),
        setHitlPayload: (payload) => set({ hitlPayload: payload }),

        reset: () =>
          set({
            ...initialState,
            // Preserve inputs so user doesn't have to re-paste on reset
            jd: get().jd,
            latexInput: get().latexInput,
            personaIds: get().personaIds,
          }),
      }),
      {
        name: "resume-optimizer-store",
        // Only persist lightweight session data
        partialize: (state) => ({
          threadId: state.threadId,
          history: state.history,
          jd: state.jd,
        }),
      }
    ),
    { name: "ResumeStore" }
  )
);
