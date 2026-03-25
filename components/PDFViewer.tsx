"use client";

/**
 * PDFViewer — renders a PDF from a URL using pdfjs-dist.
 * Only shown after the compile_node sets pdf_url in state.
 */

import { useEffect, useRef, useState } from "react";

interface PDFViewerProps {
  url: string;
}

export function PDFViewer({ url }: PDFViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function renderPage() {
      setLoading(true);
      setError(null);
      try {
        const pdfjsLib = await import("pdfjs-dist");
        // Set worker source — required for pdfjs-dist v4+
        pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
          "pdfjs-dist/build/pdf.worker.min.mjs",
          import.meta.url
        ).toString();

        const pdf = await pdfjsLib.getDocument(url).promise;
        if (cancelled) return;

        const page = await pdf.getPage(1);
        if (cancelled) return;

        const viewport = page.getViewport({ scale: 1.4 });
        const canvas = canvasRef.current;
        if (!canvas) return;

        canvas.height = viewport.height;
        canvas.width = viewport.width;
        const ctx = canvas.getContext("2d");
        if (!ctx) return;

        await page.render({ canvasContext: ctx, canvas: canvas, viewport }).promise;
      } catch (e) {
        if (!cancelled) setError(String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    renderPage();
    return () => { cancelled = true; };
  }, [url]);

  if (error) {
    return (
      <div className="border rounded-lg p-6 text-center space-y-3">
        <p className="text-sm text-red-600">Failed to load PDF preview: {error}</p>
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-primary underline"
        >
          Open PDF directly
        </a>
      </div>
    );
  }

  return (
    <div className="border rounded-lg overflow-hidden bg-muted/20 relative">
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="animate-spin h-5 w-5 border-2 border-primary border-t-transparent rounded-full" />
        </div>
      )}
      <canvas ref={canvasRef} className="w-full h-auto" />
    </div>
  );
}
