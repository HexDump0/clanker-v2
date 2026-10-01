"""How the modern-AI-CSS signals (production: clanker.review.first_layer.ai_css) separate
human verdicts. Offline: reads the frozen v2 code excerpts, no API calls.

    uv run python evals/jev/ai_css_signals.py

See AI/notes/modern-ai-css-rule-2026-10-01.md.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from clanker.review.first_layer.ai_css import REJECT_AT, modern_ai_css_signals

ROOT = Path(__file__).resolve().parents[2] / "data" / "eval" / "jev"
# Human reject comments that cite AI use (the label we want the rule to agree with).
AI_COMMENT = re.compile(r"\bAI\b|generat|vibe|chatgpt|claude|cursor|copilot|30\s*%", re.I)
CATS = ("ai_reject", "other_reject", "approved")


def rows() -> list[tuple[str, str, list[str], str]]:
    out = []
    for ds in ("dev", "holdout"):
        base = ROOT / ds
        cert_of = {}
        for line in open(base / "traces.jsonl"):
            t = json.loads(line)
            cert_of[t["trace_id"]] = t["cert_id"]
        css: dict[str, str] = {}
        for line in open(base / "evidence2.jsonl"):
            e = json.loads(line)
            files = e["files"] if isinstance(e["files"], list) else json.loads(e["files"])
            text = "\n".join(
                f["excerpt"] for f in files if f["path"].lower().endswith((".css", ".scss"))
            )
            if text:
                css[cert_of.get(e["trace_id"], "")] = text
        for r in csv.DictReader(open(base / "decisions_v2.csv")):
            if r["cert_id"] not in css:
                continue
            verdict = r["human_verdict"]
            if verdict == "APPROVED":
                cat = "approved"
            elif verdict == "REJECTED":
                cat = "ai_reject" if AI_COMMENT.search(r["human_comment"] or "") else "other_reject"
            else:
                continue
            out.append((ds, cat, modern_ai_css_signals(css[r["cert_id"]]), r["project"]))
    return out


def main() -> None:
    data = rows()
    n = {c: sum(r[1] == c for r in data) for c in CATS}
    print("CSS-bearing reviews:", n)
    names = sorted({s for r in data for s in r[2]})
    print(f"{'signal':22}" + "".join(f"{c:>14}" for c in CATS))
    for name in names:
        print(
            f"{name:22}"
            + "".join(f"{sum(name in r[2] for r in data if r[1] == c) / n[c]:>14.0%}" for c in CATS)
        )
    print()
    for at in range(2, 8):
        hits = {c: sum(len(r[2]) >= at for r in data if r[1] == c) for c in CATS}
        mark = "  <- REJECT_AT" if at == REJECT_AT else ""
        print(f">= {at}: " + "  ".join(f"{c} {hits[c]}/{n[c]}" for c in CATS) + mark)
    print("\nApproved projects closest to the limit:")
    for ds, _, sig, project in sorted(
        (r for r in data if r[1] == "approved"), key=lambda r: -len(r[2])
    )[:5]:
        print(f"  {ds:8} {len(sig)}  {project}: {', '.join(sig)}")


if __name__ == "__main__":
    main()
