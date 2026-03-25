"use client";

/**
 * DiffViewer — shows a line-by-line diff between two LaTeX strings.
 * Uses the `diff` npm package's diffLines() function.
 * Green = additions, red = deletions.
 */

import { useMemo } from "react";
import { diffLines } from "diff";

interface DiffViewerProps {
  original: string;
  modified: string;
}

export function DiffViewer({ original, modified }: DiffViewerProps) {
  const parts = useMemo(() => diffLines(original, modified), [original, modified]);

  if (!original && !modified) return null;

  return (
    <div className="border rounded-lg overflow-auto max-h-[500px] bg-white font-mono text-xs">
      <div className="sticky top-0 bg-muted/80 px-3 py-1.5 text-xs text-muted-foreground border-b flex gap-4">
        <span className="text-red-600 font-medium">- Original</span>
        <span className="text-green-600 font-medium">+ Generated</span>
      </div>
      <pre className="p-3 whitespace-pre-wrap leading-relaxed">
        {parts.map((part, i) => {
          if (part.added) {
            return (
              <span key={i} className="bg-green-50 text-green-800">
                {part.value.split("\n").map((line, j, arr) =>
                  j < arr.length - 1 || line ? (
                    <span key={j}>
                      <span className="select-none text-green-400 mr-1">+</span>
                      {line}
                      {j < arr.length - 1 ? "\n" : ""}
                    </span>
                  ) : null
                )}
              </span>
            );
          }
          if (part.removed) {
            return (
              <span key={i} className="bg-red-50 text-red-800">
                {part.value.split("\n").map((line, j, arr) =>
                  j < arr.length - 1 || line ? (
                    <span key={j}>
                      <span className="select-none text-red-400 mr-1">-</span>
                      {line}
                      {j < arr.length - 1 ? "\n" : ""}
                    </span>
                  ) : null
                )}
              </span>
            );
          }
          return (
            <span key={i} className="text-muted-foreground">
              {part.value}
            </span>
          );
        })}
      </pre>
    </div>
  );
}
