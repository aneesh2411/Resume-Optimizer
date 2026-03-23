"use client";

/**
 * ResumePreview — A4-locked PDF preview using @react-pdf/renderer.
 *
 * The PDF document is rendered at exactly A4 dimensions (595 × 842 pt).
 * Overflow is detected by comparing word_count against the 600-word budget.
 * When overflow is detected:
 *  - A red "OVERFLOW" badge appears inside the PDF
 *  - The Zustand isOverflow flag is set, blocking export
 *
 * Note: PDFViewer is client-only — it triggers a dynamic import.
 */

import { useEffect } from "react";
import {
  Document,
  Page,
  Text,
  View,
  StyleSheet,
  PDFViewer,
  Font,
} from "@react-pdf/renderer";
import { useResumeStore, type ResumeOutput } from "@/store/resumeStore";

const MAX_WORDS = 600;

// ── PDF styles ────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  page: {
    paddingTop: 40,
    paddingBottom: 40,
    paddingHorizontal: 45,
    fontFamily: "Helvetica",
    fontSize: 10,
    lineHeight: 1.5,
    color: "#111827",
  },
  overflowBadge: {
    backgroundColor: "#ef4444",
    color: "white",
    padding: "3 8",
    borderRadius: 4,
    fontSize: 8,
    fontFamily: "Helvetica-Bold",
    marginBottom: 8,
    alignSelf: "flex-start",
  },
  headline: {
    fontSize: 18,
    fontFamily: "Helvetica-Bold",
    marginBottom: 4,
    color: "#111827",
  },
  sectionTitle: {
    fontSize: 10,
    fontFamily: "Helvetica-Bold",
    textTransform: "uppercase",
    letterSpacing: 0.8,
    borderBottomWidth: 0.5,
    borderBottomColor: "#9ca3af",
    paddingBottom: 2,
    marginTop: 10,
    marginBottom: 5,
    color: "#374151",
  },
  text: {
    fontSize: 10,
    lineHeight: 1.5,
    color: "#374151",
  },
  bullet: {
    flexDirection: "row",
    marginBottom: 3,
    paddingLeft: 10,
  },
  bulletDot: {
    width: 10,
    fontSize: 10,
    color: "#374151",
  },
  bulletText: {
    flex: 1,
    fontSize: 10,
    lineHeight: 1.5,
    color: "#374151",
  },
  footer: {
    marginTop: 10,
    paddingTop: 4,
    borderTopWidth: 0.5,
    borderTopColor: "#e5e7eb",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  footerText: {
    fontSize: 7,
    color: "#9ca3af",
  },
});

// ── PDF Document component ────────────────────────────────────────────────────

function ResumePDFDocument({ draft }: { draft: ResumeOutput }) {
  const isOverflow = draft.word_count > MAX_WORDS;

  return (
    <Document>
      <Page size="A4" style={styles.page}>
        {/* Overflow badge — only shown when word count exceeds budget */}
        {isOverflow && (
          <View>
            <Text style={styles.overflowBadge}>
              ⚠ OVERFLOW — {draft.word_count - MAX_WORDS} words over budget
            </Text>
          </View>
        )}

        {/* Headline */}
        <Text style={styles.headline}>{draft.headline}</Text>

        {/* Summary */}
        <Text style={styles.sectionTitle}>Summary</Text>
        <Text style={styles.text}>{draft.summary.content}</Text>

        {/* Experience */}
        <Text style={styles.sectionTitle}>Experience</Text>
        {draft.experience.map((exp, i) => (
          <View key={i} style={styles.bullet}>
            <Text style={styles.bulletDot}>•</Text>
            <Text style={styles.bulletText}>{exp.content}</Text>
          </View>
        ))}

        {/* Skills */}
        <Text style={styles.sectionTitle}>Skills</Text>
        <Text style={styles.text}>{draft.skills.content}</Text>

        {/* Education */}
        <Text style={styles.sectionTitle}>Education</Text>
        <Text style={styles.text}>{draft.education.content}</Text>

        {/* Footer metadata */}
        <View style={styles.footer}>
          <Text style={styles.footerText}>
            Format: {draft.format_used}
          </Text>
          <Text style={styles.footerText}>
            ATS Score: {draft.ats_score_estimate}/100
          </Text>
          <Text style={styles.footerText}>
            Words: {draft.word_count}/{MAX_WORDS}
          </Text>
        </View>
      </Page>
    </Document>
  );
}

// ── Exported component ────────────────────────────────────────────────────────

export function ResumePreview() {
  const draft = useResumeStore((s) => s.draft);
  const isStreaming = useResumeStore((s) => s.isStreaming);
  const setOverflow = useResumeStore((s) => s.setOverflow);

  // Sync overflow state to Zustand whenever draft changes
  useEffect(() => {
    if (draft) {
      setOverflow(draft.word_count > MAX_WORDS);
    } else {
      setOverflow(false);
    }
  }, [draft, setOverflow]);

  if (!draft) {
    return (
      <div className="flex items-center justify-center h-[700px] border rounded-lg bg-muted/20">
        <div className="text-center space-y-2 text-muted-foreground">
          {isStreaming ? (
            <>
              <div className="animate-spin h-6 w-6 border-2 border-primary border-t-transparent rounded-full mx-auto" />
              <p className="text-sm">Generating your resume…</p>
            </>
          ) : (
            <p className="text-sm">
              Paste a job description to generate your tailored resume
            </p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg overflow-hidden border">
      <PDFViewer
        width="100%"
        height={750}
        showToolbar={false}
        className="block"
      >
        <ResumePDFDocument draft={draft} />
      </PDFViewer>
    </div>
  );
}
