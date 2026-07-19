"""Hack Club-themed PDF review reports via Typst.

v1 shelled out with ``subprocess.run`` inside an agent tool, blocking the whole
event loop for up to 30 s. Here compilation is an async subprocess, driven by
the runner from the structured ``ReviewOutput`` — the agent never touches it.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from clanker.review.models import ReviewOutput

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "review_report.typ"
COMPILE_TIMEOUT = 30.0


def _strip_scheme(url: str | None) -> str:
    return (url or "").removeprefix("https://").removeprefix("http://")


class PdfError(RuntimeError):
    pass


async def generate_review_pdf(
    review: ReviewOutput,
    *,
    output_path: Path,
    project_name: str,
    project_desc: str,
    repo_url: str | None,
    demo_url: str | None,
    project_url: str | None = None,
) -> Path:
    """Compile the review report PDF and return its path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "checks": review.checks.as_pdf_rows(),
        "required_fixes": review.required_fixes or [],
        "feedback": review.feedback or [],
        "special_flags": review.special_flags or [],
    }
    review_date = datetime.now(UTC).strftime("%-m/%-d/%y %-H:%M UTC")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(json.dumps(data))
        data_file = Path(f.name)

    inputs = {
        "verdict": review.verdict.value,
        "project_type": review.project_type,
        "reasoning": review.reasoning,
        "repo_url": _strip_scheme(repo_url),
        "demo_url": _strip_scheme(demo_url),
        "project_name": project_name,
        "project_desc": project_desc,
        "project_url": _strip_scheme(project_url),
        "review_date": review_date,
        "data_file": str(data_file),
    }
    args = ["compile", "--root", "/"]
    for key, value in inputs.items():
        args += ["--input", f"{key}={value}"]
    args += [str(TEMPLATE_PATH), str(output_path)]

    try:
        proc = await asyncio.create_subprocess_exec(
            "typst",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=COMPILE_TIMEOUT)
        except TimeoutError:
            proc.kill()
            raise PdfError(f"Typst compilation timed out after {COMPILE_TIMEOUT}s") from None
        if proc.returncode != 0:
            raise PdfError(f"Typst compilation failed: {stderr.decode(errors='replace')[:500]}")
    except FileNotFoundError:
        raise PdfError("typst binary not found — install Typst to generate PDF reports") from None
    finally:
        data_file.unlink(missing_ok=True)

    return output_path
