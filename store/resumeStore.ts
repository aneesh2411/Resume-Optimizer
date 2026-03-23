/**
 * store/resumeStore.ts — Zustand global state for the resume optimizer.
 *
 * State domains:
 * - Session: threadId, jobDescription
 * - Pipeline: isStreaming, currentNode, error
 * - Data: draft, critique, resolution, history
 * - UI: isOverflow (gates PDF export)
 *
 * Persisted to localStorage: threadId + history (lightweight — avoids re-generating on refresh)
 * Not persisted: draft, critique, resolution (re-fetched on session restore)
 */

"use client";

import { create } from "zustand";
import { devtools, persist } from "zustand/middleware";

// ── Type mirrors of the Python Pydantic schemas ───────────────────────────────

export interface ResumeSection {
  content: string;
}

export interface ResumeOutput {
  headline: string;
  summary: ResumeSection;
  experience: ResumeSection[];
  skills: ResumeSection;
  education: ResumeSection;
  format_used: "STAR" | "XYZ" | "CAR";
  ats_score_estimate: number;
  word_count: number;
}

export interface CritiqueResult {
  role: "recruiter" | "hiring_manager" | "expert";
  score: number;
  flags: string[];
  suggestions: string[];
  ai_slop_detected: boolean;
  jd_match_confidence: number;
}

export interface ConflictResolution {
  priority_flags: string[];
  consensus_score: number;
  blocking_issues: string[];
  optional_improvements: string[];
}

// ── Store interface ───────────────────────────────────────────────────────────

interface ResumeState {
  // Session
  threadId: string | null;
  jobDescription: string;

  // Pipeline progress
  isStreaming: boolean;
  currentNode: string | null;
  error: string | null;

  // Resume data
  draft: ResumeOutput | null;
  critique: CritiqueResult[];
  resolution: ConflictResolution | null;
  history: ResumeOutput[]; // previous iteration drafts

  // Single-page enforcement
  isOverflow: boolean;

  // ── Actions ──────────────────────────────────────────────────────────────

  setJobDescription: (jd: string) => void;
  setThreadId: (id: string) => void;

  setStreaming: (streaming: boolean) => void;
  setCurrentNode: (node: string | null) => void;
  setError: (error: string | null) => void;

  /**
   * Set a new resume draft. Automatically pushes the previous draft to history.
   */
  setDraft: (draft: ResumeOutput) => void;
  setCritique: (critique: CritiqueResult[]) => void;
  setResolution: (resolution: ConflictResolution) => void;

  /**
   * Update the overflow flag. When true, the Export button is disabled.
   */
  setOverflow: (overflow: boolean) => void;

  reset: () => void;
}

// ── Initial state ─────────────────────────────────────────────────────────────

const initialState: Omit<
  ResumeState,
  | "setJobDescription"
  | "setThreadId"
  | "setStreaming"
  | "setCurrentNode"
  | "setError"
  | "setDraft"
  | "setCritique"
  | "setResolution"
  | "setOverflow"
  | "reset"
> = {
  threadId: null,
  jobDescription: "",
  isStreaming: false,
  currentNode: null,
  error: null,
  draft: null,
  critique: [],
  resolution: null,
  history: [],
  isOverflow: false,
};

// ── Store ──────────────────────────────────────────────────────────────────────

export const useResumeStore = create<ResumeState>()(
  devtools(
    persist(
      (set, get) => ({
        ...initialState,

        setJobDescription: (jd) => set({ jobDescription: jd }),
        setThreadId: (id) => set({ threadId: id }),

        setStreaming: (streaming) => set({ isStreaming: streaming }),
        setCurrentNode: (node) => set({ currentNode: node }),
        setError: (error) => set({ error }),

        setDraft: (draft) => {
          const previous = get().draft;
          const history = previous
            ? [...get().history, previous]
            : get().history;
          set({ draft, history });
        },

        setCritique: (critique) => set({ critique }),
        setResolution: (resolution) => set({ resolution }),

        setOverflow: (overflow) => set({ isOverflow: overflow }),

        reset: () =>
          set({
            ...initialState,
            // Preserve job description so user doesn't have to re-paste on reset
            jobDescription: get().jobDescription,
          }),
      }),
      {
        name: "resume-optimizer-store",
        // Only persist lightweight data — avoid storing large resume blobs
        partialize: (state) => ({
          threadId: state.threadId,
          history: state.history,
          jobDescription: state.jobDescription,
        }),
      }
    ),
    { name: "ResumeStore" }
  )
);
