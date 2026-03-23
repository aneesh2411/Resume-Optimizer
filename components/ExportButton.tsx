"use client";

/**
 * ExportButton — triggers PDF export via POST /api/export.
 *
 * Disabled when:
 * - isOverflow is true (word_count > 600)
 * - No draft exists
 * - isStreaming is true
 *
 * The button sends the resume as an HTML string (serialised from the draft data)
 * to /api/export, which uses Puppeteer to render a pixel-perfect A4 PDF.
 */

import { useState, useCallback } from "react";
import { useResumeStore } from "@/store/resumeStore";

function buildResumeHTML(draft: NonNullable<ReturnType<typeof useResumeStore>["draft"]>): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Resume</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 10pt;
    line-height: 1.5;
    color: #111827;
    padding: 20mm 15mm;
    width: 210mm;
    min-height: 297mm;
  }
  h1 { font-size: 18pt; font-weight: 700; margin-bottom: 4pt; }
  h2 {
    font-size: 9pt;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8pt;
    border-bottom: 0.5pt solid #9ca3af;
    padding-bottom: 2pt;
    margin-top: 10pt;
    margin-bottom: 5pt;
    color: #374151;
  }
  p { font-size: 10pt; color: #374151; margin-bottom: 3pt; }
  ul { list-style: none; padding: 0; }
  li::before { content: "• "; }
  li { font-size: 10pt; color: #374151; margin-bottom: 3pt; padding-left: 10pt; text-indent: -10pt; }
  .footer {
    margin-top: 10pt;
    padding-top: 4pt;
    border-top: 0.5pt solid #e5e7eb;
    display: flex;
    justify-content: space-between;
    font-size: 7pt;
    color: #9ca3af;
  }
</style>
</head>
<body>
  <h1>${escapeHtml(draft.headline)}</h1>

  <h2>Summary</h2>
  <p>${escapeHtml(draft.summary.content)}</p>

  <h2>Experience</h2>
  <ul>
    ${draft.experience.map((e) => `<li>${escapeHtml(e.content)}</li>`).join("\n    ")}
  </ul>

  <h2>Skills</h2>
  <p>${escapeHtml(draft.skills.content)}</p>

  <h2>Education</h2>
  <p>${escapeHtml(draft.education.content)}</p>

  <div class="footer">
    <span>Format: ${escapeHtml(draft.format_used)}</span>
    <span>ATS Score: ${draft.ats_score_estimate}/100</span>
    <span>Words: ${draft.word_count}/600</span>
  </div>
</body>
</html>`;
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

export function ExportButton() {
  const draft = useResumeStore((s) => s.draft);
  const threadId = useResumeStore((s) => s.threadId);
  const isOverflow = useResumeStore((s) => s.isOverflow);
  const isStreaming = useResumeStore((s) => s.isStreaming);

  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const isDisabled = !draft || isOverflow || isStreaming || isExporting;

  const handleExport = useCallback(async () => {
    if (!draft || isOverflow) return;
    setIsExporting(true);
    setExportError(null);

    try {
      const html = buildResumeHTML(draft);
      const res = await fetch("/api/export", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(isOverflow ? { "X-Page-Overflow": "true" } : {}),
        },
        body: JSON.stringify({ html, threadId }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: "Export failed" })) as { error?: string };
        throw new Error(err.error ?? "Export failed");
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `resume-${threadId ?? "download"}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(String(err));
    } finally {
      setIsExporting(false);
    }
  }, [draft, isOverflow, threadId]);

  return (
    <div className="space-y-2">
      <button
        onClick={handleExport}
        disabled={isDisabled}
        className="w-full py-2.5 px-4 text-sm font-medium rounded-lg bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        title={
          isOverflow
            ? "Fix page overflow before exporting"
            : !draft
            ? "Generate a resume first"
            : "Export as PDF"
        }
      >
        {isExporting ? (
          <span className="flex items-center justify-center gap-2">
            <span className="animate-spin h-3.5 w-3.5 border-2 border-current border-t-transparent rounded-full" />
            Generating PDF…
          </span>
        ) : isOverflow ? (
          "Export Blocked — Fix Overflow"
        ) : (
          "Export as PDF"
        )}
      </button>

      {isOverflow && (
        <p className="text-xs text-red-500 text-center">
          Word count exceeds 600 — PDF export is blocked until you re-compress or reduce content.
        </p>
      )}

      {exportError && (
        <p className="text-xs text-red-500 text-center">Export failed: {exportError}</p>
      )}
    </div>
  );
}
