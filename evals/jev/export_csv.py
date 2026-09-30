"""Write one CSV row per review: human vs DeepSeek vs first-layer Clanker+Jev.

    JEV_DATASET=holdout uv run python evals/jev/export_csv.py   # -> data/eval/jev/holdout/decisions.csv
"""

from __future__ import annotations

import csv
import json
import re

from common import DATA
from questions_reject import JEV_REASONS, reject_decision
from report_layer import THRESHOLDS, load


def main() -> None:
    labels, traces, results, ids, facts = load()
    thresholds = json.loads(THRESHOLDS.read_text())
    out = DATA / "decisions.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            ["cert_id", "project", "demo_url", "reviewed_at", "human_verdict", "human_comment",
             "deepseek_verdict", "clanker_jev", "clanker_reasons", "jev_main_reason"]
            + [f"p_{k}" for k in JEV_REASONS]
            + ["jev_latency_s", "jev_tokens"]
        )
        for i in sorted(ids, key=lambda x: traces[x]["start_timestamp"]):
            t, r = traces[i], results[i]
            prompt = t["messages"][0]["parts"][0]["content"]
            name = re.search(r"^- Project name: (.*)$", prompt, re.M)
            demo = re.search(r"^- Demo URL: (.*)$", prompt, re.M)
            label = labels[t["cert_id"]]
            verdict, reasons = reject_decision(r["answers"], facts[i], thresholds)
            w.writerow(
                [t["cert_id"], name.group(1) if name else "", demo.group(1) if demo else "",
                 t["start_timestamp"], label["human_verdict"],
                 (label.get("human_comment") or "").replace("\n", " "),
                 t["verdict"], verdict, ";".join(reasons), r["answers"]["main_reason"]["choice"]]
                + [r["answers"][k]["noul"] for k in JEV_REASONS]
                + [r["latency_s"], (r.get("usage") or {}).get("input_tokens")]
            )
    print(f"wrote {len(ids)} rows -> {out}")


if __name__ == "__main__":
    main()
