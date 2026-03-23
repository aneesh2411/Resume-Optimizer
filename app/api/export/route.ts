/**
 * POST /api/export
 *
 * Generates a pixel-perfect A4 PDF from an HTML string using Puppeteer.
 *
 * Uses @sparticuz/chromium for Vercel serverless compatibility
 * (full Puppeteer fails on Vercel's read-only Lambda runtime).
 *
 * Safety: rejects requests with the X-Page-Overflow: true header —
 * the frontend sets this flag when word_count > 600.
 */

import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const maxDuration = 60;

interface ExportRequest {
  html: string;
  threadId?: string;
}

export async function POST(req: NextRequest): Promise<NextResponse> {
  // Block export if the frontend detected page overflow
  if (req.headers.get("X-Page-Overflow") === "true") {
    return NextResponse.json(
      { error: "Page overflow detected — reduce content before exporting" },
      { status: 400 }
    );
  }

  const { html, threadId = "resume" }: ExportRequest = await req.json();

  if (!html || typeof html !== "string") {
    return NextResponse.json({ error: "html is required" }, { status: 400 });
  }

  let browser: import("puppeteer-core").Browser | null = null;

  try {
    // Dynamic import to keep these out of the bundle on the client side
    const chromium = (await import("@sparticuz/chromium")).default;
    const puppeteer = (await import("puppeteer-core")).default;

    browser = await puppeteer.launch({
      args: chromium.args,
      defaultViewport: chromium.defaultViewport,
      executablePath: await chromium.executablePath(),
      headless: chromium.headless as boolean,
    });

    const page = await browser.newPage();

    // Set content and wait for fonts / images to settle
    await page.setContent(html, { waitUntil: "networkidle0", timeout: 30_000 });

    const pdfBuffer = await page.pdf({
      format: "A4",
      printBackground: true,
      margin: {
        top: "20mm",
        bottom: "20mm",
        left: "15mm",
        right: "15mm",
      },
    });

    return new NextResponse(Buffer.from(pdfBuffer), {
      headers: {
        "Content-Type": "application/pdf",
        "Content-Disposition": `attachment; filename="resume-${threadId}.pdf"`,
        "Content-Length": String(pdfBuffer.length),
      },
    });
  } catch (err) {
    console.error("[/api/export] Puppeteer error:", err);
    return NextResponse.json(
      { error: "PDF generation failed", detail: String(err) },
      { status: 500 }
    );
  } finally {
    if (browser) {
      await browser.close().catch(() => {});
    }
  }
}
