"use client";

/**
 * ExportButton — downloads the compiled PDF from the Azure Blob URL.
 *
 * Shown only after compile_node sets pdf_url in state.
 * No server round-trip needed — just a direct link download.
 */

import { useResumeStore } from "@/store/resumeStore";

export function ExportButton() {
  const pdfUrl = useResumeStore((s) => s.pdfUrl);
  const threadId = useResumeStore((s) => s.threadId);
  const isStreaming = useResumeStore((s) => s.isStreaming);

  if (!pdfUrl) return null;

  const filename = `resume-${threadId ?? "download"}.pdf`;

  return (
    <a
      href={pdfUrl}
      download={filename}
      target="_blank"
      rel="noopener noreferrer"
      className={`block w-full text-center py-2.5 px-4 text-sm font-medium rounded-lg bg-green-600 text-white hover:bg-green-700 transition-colors ${
        isStreaming ? "opacity-50 pointer-events-none" : ""
      }`}
    >
      Download PDF
    </a>
  );
}
