/**
 * Unit tests for the Zustand resume store.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { useResumeStore } from "./resumeStore";
import type { ResumeOutput, CritiqueResult, ConflictResolution } from "./resumeStore";

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeDraft(wordCount = 300): ResumeOutput {
  return {
    headline: "Senior Software Engineer",
    summary: { content: "5 years Python, distributed systems." },
    experience: [{ content: "Built APIs handling 10k req/s. Reduced latency 30%." }],
    skills: { content: "Python, FastAPI, PostgreSQL" },
    education: { content: "BSc CS, MIT 2018" },
    format_used: "XYZ",
    ats_score_estimate: 80,
    word_count: wordCount,
  };
}

function makeCritique(): CritiqueResult[] {
  return [
    {
      role: "recruiter",
      score: 75,
      flags: ["Missing keyword: Python"],
      suggestions: ["Add Python to skills"],
      ai_slop_detected: false,
      jd_match_confidence: 80,
    },
  ];
}

// ── Tests ──────────────────────────────────────────────────────────────────────

describe("resumeStore", () => {
  beforeEach(() => {
    // Reset store to initial state before each test
    useResumeStore.getState().reset();
  });

  it("initialises with empty state", () => {
    const state = useResumeStore.getState();
    expect(state.draft).toBeNull();
    expect(state.critique).toEqual([]);
    expect(state.isOverflow).toBe(false);
    expect(state.threadId).toBeNull();
    expect(state.history).toEqual([]);
  });

  it("setDraft updates draft and pushes previous to history", () => {
    const store = useResumeStore.getState();
    const first = makeDraft(200);
    const second = makeDraft(300);

    store.setDraft(first);
    expect(useResumeStore.getState().draft).toEqual(first);
    expect(useResumeStore.getState().history).toHaveLength(0);

    store.setDraft(second);
    expect(useResumeStore.getState().draft).toEqual(second);
    expect(useResumeStore.getState().history).toHaveLength(1);
    expect(useResumeStore.getState().history[0]).toEqual(first);
  });

  it("setOverflow(true) blocks export correctly", () => {
    const store = useResumeStore.getState();
    store.setOverflow(true);
    expect(useResumeStore.getState().isOverflow).toBe(true);
  });

  it("setOverflow(false) unblocks export", () => {
    const store = useResumeStore.getState();
    store.setOverflow(true);
    store.setOverflow(false);
    expect(useResumeStore.getState().isOverflow).toBe(false);
  });

  it("setCritique stores critique results", () => {
    const critique = makeCritique();
    useResumeStore.getState().setCritique(critique);
    expect(useResumeStore.getState().critique).toEqual(critique);
  });

  it("setResolution stores conflict resolution", () => {
    const resolution: ConflictResolution = {
      priority_flags: ["Missing keyword"],
      consensus_score: 78,
      blocking_issues: ["No quantified achievements"],
      optional_improvements: ["Add LinkedIn profile"],
    };
    useResumeStore.getState().setResolution(resolution);
    expect(useResumeStore.getState().resolution).toEqual(resolution);
  });

  it("reset clears draft, critique, and overflow but preserves jobDescription", () => {
    const store = useResumeStore.getState();
    store.setJobDescription("Python engineer role");
    store.setDraft(makeDraft());
    store.setCritique(makeCritique());
    store.setOverflow(true);
    store.setThreadId("thread-123");

    store.reset();

    const state = useResumeStore.getState();
    expect(state.draft).toBeNull();
    expect(state.critique).toEqual([]);
    expect(state.isOverflow).toBe(false);
    // jobDescription is preserved across reset to avoid re-pasting
    expect(state.jobDescription).toBe("Python engineer role");
  });

  it("setThreadId stores thread ID", () => {
    useResumeStore.getState().setThreadId("abc-123");
    expect(useResumeStore.getState().threadId).toBe("abc-123");
  });

  it("setError stores error message", () => {
    useResumeStore.getState().setError("Pipeline unavailable");
    expect(useResumeStore.getState().error).toBe("Pipeline unavailable");
  });

  it("setError(null) clears error", () => {
    const store = useResumeStore.getState();
    store.setError("Something went wrong");
    store.setError(null);
    expect(useResumeStore.getState().error).toBeNull();
  });
});
