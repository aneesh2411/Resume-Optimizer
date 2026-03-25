import io
import subprocess
import tempfile
import os

from pypdf import PdfReader

from models import CompileJob


def compile_latex(job: CompileJob) -> tuple[bool, bytes, str, int]:
    """
    Compiles LaTeX content to PDF using tectonic.
    Returns (success: bool, pdf_bytes_or_empty: bytes, error_log: str, page_count: int)
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tex_file = os.path.join(tmpdir, "resume.tex")
        pdf_file = os.path.join(tmpdir, "resume.pdf")

        with open(tex_file, "w", encoding="utf-8") as f:
            f.write(job.latex_content)

        result = subprocess.run(
            [
                "tectonic",
                "--outdir", tmpdir,
                "--keep-logs",
                "--print",
                tex_file,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "TECTONIC_CACHE_DIR": "/tmp/tectonic-cache"},
        )

        if result.returncode != 0:
            return False, b"", result.stderr + result.stdout, 0

        if not os.path.exists(pdf_file):
            return False, b"", "Compile succeeded but PDF not found", 0

        # Read PDF bytes before tmpdir cleanup
        with open(pdf_file, "rb") as f:
            pdf_bytes = f.read()

    # Count pages via pypdf
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        page_count = len(reader.pages)
    except Exception:
        page_count = 1  # conservative default

    return True, pdf_bytes, "", page_count
