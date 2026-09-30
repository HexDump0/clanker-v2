"""Compare DeepSeek and the Jev arms against human per-attempt verdicts.

    uv run python evals/jev/report.py [--gate 0.6]
"""

from __future__ import annotations

import argparse
from collections import Counter

from common import DATA, LABELS, RESULTS, TRACES, read_jsonl

DEEPSEEK_IN, DEEPSEEK_CACHE, DEEPSEEK_OUT = 0.13e-6, 0.07e-6, 0.28e-6  # CoreWeave list prices
JEV_IN = 0.042e-6


def holistic(answers: dict, gate: float) -> str:
    v = answers["verdict"]
    if v["confidence"] < gate:
        return "FLAG_FOR_HUMAN"
    return "APPROVE" if v["choice"] == "approve" else "REJECT"


def approvable(answers: dict, lo: float, hi: float) -> str:
    """Noul variant: approve above hi, reject below lo, flag in between."""
    x = answers["approvable"]["noul"]
    return "APPROVE" if x >= hi else "REJECT" if x < lo else "FLAG_FOR_HUMAN"


def score(name: str, rows: list[tuple[str, str]]) -> dict:
    """rows: (system verdict, human verdict APPROVED/REJECTED)."""
    n = len(rows)
    decided = [(s, h) for s, h in rows if s != "FLAG_FOR_HUMAN"]
    correct = sum((s == "APPROVE") == (h == "APPROVED") for s, h in decided)
    false_approve = sum(s == "APPROVE" and h == "REJECTED" for s, h in decided)
    false_reject = sum(s == "REJECT" and h == "APPROVED" for s, h in decided)
    human_rej = sum(h == "REJECTED" for _, h in rows)
    caught_rej = sum(s == "REJECT" and h == "REJECTED" for s, h in rows)
    return {
        "system": name,
        "n": n,
        "coverage": len(decided) / n if n else 0,
        "acc_decided": correct / len(decided) if decided else 0,
        "false_approve": false_approve,
        "false_reject": false_reject,
        "reject_recall": caught_rej / human_rej if human_rej else 0,
        "flagged": n - len(decided),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", type=float, default=0.6)
    parser.add_argument("--arms", default="packet,bunny")
    args = parser.parse_args()
    arms = args.arms.split(",")

    labels = {
        r["cert_id"]: r["human_verdict"]
        for r in read_jsonl(LABELS)
        if r.get("human_verdict") in ("APPROVED", "REJECTED")
    }
    traces = {t["trace_id"]: t for t in read_jsonl(TRACES)}
    results: dict[tuple[str, str], dict] = {}
    for r in read_jsonl(RESULTS):
        if "error" not in r:
            results[(r["trace_id"], r["arm"])] = r

    common_ids = [
        tid for tid, t in traces.items()
        if t["cert_id"] in labels and all((tid, a) in results for a in arms)
    ]
    print(f"labeled traces with all arms {arms}: {len(common_ids)}  "
          f"(human mix: {Counter(labels[traces[t]['cert_id']] for t in common_ids)})")

    systems: dict[str, list[tuple[str, str]]] = {}
    for tid in common_ids:
        t = traces[tid]
        human = labels[t["cert_id"]]
        systems.setdefault("deepseek_agent", []).append((t["verdict"], human))
        for arm in arms:
            r = results[(tid, arm)]
            systems.setdefault(f"jev_{arm}_rules", []).append((r["rule_verdict"], human))
            systems.setdefault(f"jev_{arm}_holistic@{args.gate}", []).append(
                (holistic(r["answers"], args.gate), human)
            )
            systems.setdefault(f"jev_{arm}_holistic_nogate", []).append(
                (holistic(r["answers"], 0.0), human)
            )
            if "approvable" in r["answers"]:
                systems.setdefault(f"jev_{arm}_approvable@0.5", []).append(
                    (approvable(r["answers"], 0.5, 0.5), human)
                )
                systems.setdefault(f"jev_{arm}_approvable_band", []).append(
                    (approvable(r["answers"], 0.3, 0.7), human)
                )

    header = f"{'system':32} {'n':>4} {'cover':>6} {'acc':>6} {'FA':>4} {'FR':>4} {'rejRec':>7} {'flag':>5}"
    print(header)
    for name, rows in systems.items():
        s = score(name, rows)
        print(f"{name:32} {s['n']:>4} {s['coverage']:>6.0%} {s['acc_decided']:>6.0%} "
              f"{s['false_approve']:>4} {s['false_reject']:>4} {s['reject_recall']:>7.0%} {s['flagged']:>5}")
    base = [("REJECT", h) for _, h in next(iter(systems.values()))]
    b = score("always_reject", base)
    print(f"{'always_reject (baseline)':32} {b['n']:>4} {b['coverage']:>6.0%} {b['acc_decided']:>6.0%} "
          f"{b['false_approve']:>4} {b['false_reject']:>4} {b['reject_recall']:>7.0%} {b['flagged']:>5}")
    print("FA = approved but human rejected · FR = rejected but human approved")

    # Ranking quality: does the approve-score separate human approvals from rejections?
    print("\nAUC (0.5 = coin flip, 1.0 = perfect separation):")
    ds_map = {"APPROVE": 1.0, "FLAG_FOR_HUMAN": 0.5, "REJECT": 0.0}
    print(f"  deepseek verdict                 {auc([(ds_map[traces[i]['verdict']], labels[traces[i]['cert_id']] == 'APPROVED') for i in common_ids]):.2f}")
    for arm in arms:
        rs = [(results[(i, arm)], labels[traces[i]['cert_id']] == "APPROVED") for i in common_ids]
        pv = auc([(r["answers"]["verdict"]["probabilities"]["approve"], y) for r, y in rs])
        line = f"  jev_{arm} verdict P(approve)      {pv:.2f}"
        if all("approvable" in r["answers"] for r, _ in rs):
            line += f" · approvable noul {auc([(r['answers']['approvable']['noul'], y) for r, y in rs]):.2f}"
        rule_map = {"APPROVE": 1.0, "FLAG_FOR_HUMAN": 0.5, "REJECT": 0.0}
        line += f" · rules {auc([(rule_map[r['rule_verdict']], y) for r, y in rs]):.2f}"
        print(line)

    # Operating curve for Jev P(approve): approve if >= t, else reject.
    for arm in arms:
        rs = [(results[(i, arm)]["answers"]["verdict"]["probabilities"]["approve"],
               labels[traces[i]["cert_id"]]) for i in common_ids]
        print(f"\njev_{arm} P(approve) threshold sweep:   t    approve  FA  FR  acc")
        for t in (0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5):
            fa = sum(p >= t and h == "REJECTED" for p, h in rs)
            fr = sum(p < t and h == "APPROVED" for p, h in rs)
            appr = sum(p >= t for p, _ in rs)
            print(f"{'':38}{t:<5}{appr:>6}{fa:>5}{fr:>4}{1 - (fa + fr) / len(rs):>6.0%}")

    # Cost / latency per review.
    ds_cost = [
        ((t["input_tokens"] - (t["cache_tokens"] or 0)) * DEEPSEEK_IN
         + (t["cache_tokens"] or 0) * DEEPSEEK_CACHE + t["output_tokens"] * DEEPSEEK_OUT)
        for t in (traces[i] for i in common_ids)
    ]
    ds_time = [traces[i]["duration"] for i in common_ids]
    print(f"\ndeepseek agent: avg ${sum(ds_cost) / len(ds_cost):.5f}/review, "
          f"avg {sum(ds_time) / len(ds_time):.1f}s (agent only, CoreWeave prices)")
    bunny = {b["trace_id"]: b for b in read_jsonl(DATA / "bunny.jsonl") if "error" not in b}
    if "bunny" in arms:
        bs = [bunny[i] for i in common_ids if i in bunny]
        lat = sorted(b["latency_s"] for b in bs)
        print(f"space bunny investigation (free): avg {sum(b['input_tokens'] for b in bs) / len(bs):.0f} in / "
              f"{sum(b['output_tokens'] for b in bs) / len(bs):.0f} out tokens, "
              f"{sum(b['requests'] for b in bs) / len(bs):.1f} requests, "
              f"p50 {lat[len(lat) // 2]:.1f}s p90 {lat[int(len(lat) * 0.9)]:.1f}s")
    for arm in arms:
        rs = [results[(i, arm)] for i in common_ids]
        toks = [r["usage"].get("input_tokens") or 0 for r in rs]
        lat = sorted(r["latency_s"] for r in rs)
        print(f"jev {arm}: avg {sum(toks) / len(toks):.0f} tokens, ${sum(toks) / len(toks) * JEV_IN:.5f}/call, "
              f"p50 {lat[len(lat) // 2]:.2f}s p90 {lat[int(len(lat) * 0.9)]:.2f}s")


def auc(pairs: list[tuple[float, bool]]) -> float:
    """P(score of a human-approved attempt > score of a human-rejected one)."""
    pos = [s for s, y in pairs if y]
    neg = [s for s, y in pairs if not y]
    if not pos or not neg:
        return float("nan")
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


if __name__ == "__main__":
    main()
