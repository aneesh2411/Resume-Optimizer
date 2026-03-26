"""
Test the /compile-direct endpoint end-to-end.
Run with: python test_compile.py
Requires the container to be running: docker run -p 8000:8000 latex-compiler
"""
import json
import sys

try:
    import httpx
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx"])
    import httpx

SAMPLE_LATEX = r"""
\documentclass{article}
\begin{document}
\textbf{John Smith} --- Software Engineer \\
john@example.com | github.com/johnsmith \\[6pt]
\textbf{Experience} \\
Senior Engineer, Acme Corp (2021--present) \\
Built distributed systems serving 10M users.
\end{document}
"""

payload = {
    "job_id": "test-001",
    "latex_content": SAMPLE_LATEX,
    "user_id": "test-user",
}

print("Sending compile job to http://localhost:8000/compile-direct ...")

try:
    response = httpx.post(
        "http://localhost:8000/compile-direct",
        json=payload,
        timeout=90,
    )
    response.raise_for_status()
    result = response.json()
    print(json.dumps(result, indent=2))

    if result.get("success"):
        print(f"\nPDF URL: {result['pdf_url']}")
    else:
        print(f"\nCompile failed: {result.get('error', 'unknown error')}")
        sys.exit(1)

except httpx.ConnectError:
    print("ERROR: Could not connect to localhost:8000.")
    print("Make sure the container is running:")
    print("  docker run --env-file ../.env.local -p 8000:8000 latex-compiler")
    sys.exit(1)
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
