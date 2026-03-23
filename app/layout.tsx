import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Resume Optimizer — AI-Powered ATS Tailoring",
  description:
    "Tailor your resume to any job description with AI. Get multi-persona critique from a recruiter, hiring manager, and industry expert. Single-page, ATS-optimized output every time.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased min-h-screen bg-background text-foreground">
        {children}
      </body>
    </html>
  );
}
