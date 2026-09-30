"""Generate the Shipwright-style reject message for every v2 reject, next to the human comment.

    JEV_DATASET=holdout uv run --with typesafe-sdk==0.7.2 python evals/jev/messages.py
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from common import DATA, LABELS, RESULTS, TRACES, read_jsonl
from questions_reject import reject_decision
from state import build_states

from clanker.review.reject_message import RejectContext, compose_reject_message

V2 = json.loads((Path(__file__).parent / "thresholds_conservative2.json").read_text())
STYLE = (".css", ".scss", ".sass", ".less")


def main() -> None:
    labels = {r["cert_id"]: r for r in read_jsonl(LABELS)}
    traces = {t["trace_id"]: t for t in read_jsonl(TRACES)}
    results = {r["trace_id"]: r for r in read_jsonl(RESULTS)
               if r.get("arm") == "reject2" and "error" not in r}
    ev2 = {e["trace_id"]: e for e in read_jsonl(DATA / "evidence2.jsonl")}
    out = DATA / "messages_v2.csv"
    n = 0
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["cert_id", "project", "human_verdict", "reasons", "clanker_message",
                    "human_comment"])
        for tid, r in results.items():
            t, e = traces[tid], ev2.get(tid)
            if e is None:
                continue
            facts = build_states(t, ev2=e)["facts"]
            verdict, reasons = reject_decision(r["answers"], facts, V2)
            if verdict != "REJECT":
                continue
            prompt = t["messages"][0]["parts"][0]["content"]
            field = lambda k: (m.group(1).strip() if (m := re.search(rf"^- {k}: (.*)$", prompt, re.M)) else None)  # noqa: E731
            ctx = RejectContext(
                submitter=(field("Submitter") or "").strip() or None,
                repo_url=field("Repo URL"),
                readme_url=field("Readme URL"),
                demo_url=field("Demo URL"),
                project_type=r["answers"]["project_type"]["choice"],
                banner_label=facts.get("banner_label"),
                bad_hosts=facts["demo_url_rejected_platforms"],
                ai_style_file=any(f["path"].lower().endswith(STYLE) for f in e.get("files") or []),
            )
            label = labels.get(t["cert_id"], {})
            w.writerow([t["cert_id"], facts["project_name"], label.get("human_verdict"),
                        ";".join(reasons), compose_reject_message(reasons, ctx, t["cert_id"]),
                        (label.get("human_comment") or "").replace("\n", " ")])
            n += 1
    print(f"wrote {n} messages -> {out}")


if __name__ == "__main__":
    main()
