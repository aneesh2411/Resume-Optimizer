"""
analyze_latex_node — pure-regex structural analysis of the LaTeX input.

No LLM calls. Extracts:
- Total bullet count (\\item occurrences)
- Average words per bullet
- Section and subsection names
- Total word count (LaTeX commands stripped)
- Keyword gaps: capitalized terms in the JD that are absent from the LaTeX

Used downstream to inform the generate_node prompt and to populate
DensityMeter metrics in the frontend.
"""

from __future__ import annotations

import re

from pipeline.schemas import GraphState, LaTeXAnalysis


_SECTION_RE = re.compile(r"\\(?:section|subsection)\*?\{([^}]+)\}")
_ITEM_RE = re.compile(
    r"\\item\s+(.+?)(?=\\item|\\end\{(?:itemize|enumerate)\})",
    re.DOTALL,
)


def analyze_latex(latex: str, jd: str) -> LaTeXAnalysis:
    """Extract structural metrics from a LaTeX document string."""
    bullets = _ITEM_RE.findall(latex)
    bullet_words = [len(b.split()) for b in bullets]
    sections = _SECTION_RE.findall(latex)

    # Strip LaTeX commands for word count
    clean = re.sub(r"\\[a-zA-Z]+\{[^}]*\}", "", latex)
    clean = re.sub(r"\\[a-zA-Z]+", "", clean)
    words = clean.split()

    # Keyword gaps: capitalised terms from JD not found anywhere in the LaTeX
    jd_keywords = re.findall(r"\b[A-Z][a-zA-Z+#.]{2,}\b", jd)
    seen: dict[str, None] = {}
    unique_keywords = [k for k in jd_keywords if not (k in seen or seen.update({k: None}))]  # type: ignore[func-returns-value]
    gaps = [k for k in unique_keywords if k.lower() not in latex.lower()]

    return LaTeXAnalysis(
        total_bullets=len(bullets),
        avg_bullet_words=sum(bullet_words) / max(len(bullet_words), 1),
        section_count=len(sections),
        total_words=len(words),
        sections=sections,
        keyword_gaps=gaps[:10],
    )


async def analyze_latex_node(state: GraphState) -> dict:
    """Run pure-regex LaTeX analysis and store metrics in state."""
    jd = state.get("jd_compressed") or state["jd_raw"]
    return {"latex_analysis": analyze_latex(state["latex_input"], jd)}
