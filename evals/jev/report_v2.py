"""v1 vs v2 first-layer comparison (v2 = banner + demo code checks + cheap checks + richer code
excerpts + demo_broken/needs_api_key switched on). Also writes decisions_v2.csv.

    JEV_DATASET=holdout uv run --with typesafe-sdk==0.7.2 python evals/jev/report_v2.py
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from common import DATA, DATASET, LABELS, RESULTS, TRACES, read_jsonl
from questions_reject import JEV_REASONS, reject_decision
from state import build_states

HERE = Path(__file__).parent
V1 = json.loads((HERE / "thresholds_conservative.json").read_text())
V2 = json.loads((HERE / "thresholds_conservative2.json").read_text())


def line(name: str, decided: dict[str, tuple[str, list[str]]], human: dict[str, str]) -> None:
    rej = [i for i, (d, _) in decided.items() if d == "REJECT"]
    ok = sum(human[i] == "REJECTED" for i in rej)
    n_rej = sum(h == "REJECTED" for h in human.values())
    n_app = len(human) - n_rej
    prec = f"{ok / len(rej):.0%}" if rej else "-"
    print(f"{name:40} rejects {len(rej):>3}  precision {prec:>4}  caught {ok:>3}/{n_rej} "
          f"({ok / n_rej:.0%})  good bounced {len(rej) - ok:>2}/{n_app}")


def main() -> None:
    labels = {r["cert_id"]: r for r in read_jsonl(LABELS)
              if r.get("human_verdict") in ("APPROVED", "REJECTED")}
    traces = {t["trace_id"]: t for t in read_jsonl(TRACES) if t["cert_id"] in labels}
    res: dict[str, dict[str, dict]] = {"reject": {}, "reject2": {}}
    for r in read_jsonl(RESULTS):
        if r.get("arm") in res and "error" not in r:
            res[r["arm"]][r["trace_id"]] = r
    ev2 = {e["trace_id"]: e for e in read_jsonl(DATA / "evidence2.jsonl")}
    ids = [i for i in traces if i in res["reject"] and i in res["reject2"] and i in ev2]
    human = {i: labels[traces[i]["cert_id"]]["human_verdict"] for i in ids}
    f1 = {i: build_states(traces[i])["facts"] for i in ids}
    f2 = {i: build_states(traces[i], ev2=ev2[i])["facts"] for i in ids}
    print(f"dataset={DATASET}  n={len(ids)}  human={dict(Counter(human.values()))}\n")

    a1 = {i: res["reject"][i]["answers"] for i in ids}
    a2 = {i: res["reject2"][i]["answers"] for i in ids}
    ds = {i: ("REJECT" if traces[i]["verdict"] == "REJECT" else "PASS", []) for i in ids}
    v1 = {i: reject_decision(a1[i], f1[i], V1) for i in ids}
    v2 = {i: reject_decision(a2[i], f2[i], V2) for i in ids}
    v2_code = {i: reject_decision(a2[i], f2[i], {}) for i in ids}
    no_banner = {i: (("REJECT" if [r for r in v2[i][1] if not r.startswith("banner")] else "PASS"),
                     [r for r in v2[i][1] if not r.startswith("banner")]) for i in ids}

    line("deepseek (REJECT verdicts)", ds, human)
    line("v1: code + jev conservative", v1, human)
    line("v2: code rules only (no jev thresholds)", v2_code, human)
    line("v2: full (conservative2)", v2, human)
    line("v2: full minus banner check", no_banner, human)

    print("\nv2 per-reason (fires / humans agreed), a review can have several:")
    fires, good = Counter(), Counter()
    for i in ids:
        for r in v2[i][1]:
            fires[r] += 1
            good[r] += human[i] == "REJECTED"
    for r, n in fires.most_common():
        print(f"  {r:20} {n:>3}  {good[r] / n:>5.0%}")
    banners = Counter(f2[i].get("banner_label") for i in ids)
    print(f"\nbanner labels: {dict(banners)}")

    out = DATA / "decisions_v2.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["cert_id", "project", "demo_url", "human_verdict", "human_comment", "deepseek",
                    "v1", "v1_reasons", "v2", "v2_reasons", "banner_label", "project_type"]
                   + [f"p_{k}" for k in JEV_REASONS])
        for i in ids:
            w.writerow([traces[i]["cert_id"], f2[i]["project_name"], f2[i]["demo_url"], human[i],
                        (labels[traces[i]["cert_id"]].get("human_comment") or "").replace("\n", " "),
                        traces[i]["verdict"], v1[i][0], ";".join(v1[i][1]), v2[i][0],
                        ";".join(v2[i][1]), f2[i].get("banner_label"),
                        a2[i]["project_type"]["choice"]]
                       + [a2[i][k]["noul"] for k in JEV_REASONS])
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
