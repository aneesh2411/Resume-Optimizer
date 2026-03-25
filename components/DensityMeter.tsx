"use client";

/**
 * DensityMeter — visual word budget indicator.
 *
 * Shows the current word count against the 600-word single-page budget.
 * Colour codes: green < 75%, yellow < 90%, red ≥ 90%.
 */

import { useResumeStore } from "@/store/resumeStore";
import { cn } from "@/lib/utils";

const MAX_WORDS = 600;

export function DensityMeter() {
  const latexOutput = useResumeStore((s) => s.latexOutput);
  const count = latexOutput?.word_count ?? 0;
  const pct = Math.min((count / MAX_WORDS) * 100, 100);
  const isOverBudget = count > MAX_WORDS;

  const barColour =
    pct < 75 ? "bg-green-500" : pct < 90 ? "bg-yellow-500" : "bg-red-500";

  return (
    <div className="space-y-1.5">
      <div className="flex justify-between items-center text-xs text-muted-foreground">
        <span className="font-medium">Word Budget</span>
        <span className={cn("tabular-nums", isOverBudget && "text-red-500 font-bold")}>
          {count.toLocaleString()} / {MAX_WORDS.toLocaleString()}
        </span>
      </div>

      <div className="h-2 bg-muted rounded-full overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all duration-500", barColour)}
          style={{ width: `${pct}%` }}
          role="progressbar"
          aria-valuenow={count}
          aria-valuemin={0}
          aria-valuemax={MAX_WORDS}
        />
      </div>

      {isOverBudget && (
        <p className="text-xs text-red-500 font-medium">
          Over budget by {count - MAX_WORDS} words — compression will run automatically.
        </p>
      )}

      {latexOutput && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground pt-0.5">
          <span>ATS Score</span>
          <span
            className={cn(
              "font-semibold tabular-nums",
              latexOutput.ats_score_estimate >= 80
                ? "text-green-600"
                : latexOutput.ats_score_estimate >= 60
                ? "text-yellow-600"
                : "text-red-600"
            )}
          >
            {latexOutput.ats_score_estimate}/100
          </span>
          <span>•</span>
          <span>Format: {latexOutput.format_used}</span>
        </div>
      )}
    </div>
  );
}
