"""First-layer report: Clanker only REJECTs what it can confidently establish; the rest PASSes
to a human. What matters: how many rejects, how often humans agree (precision), how much of
the human reject load it removes (recall), and how many good projects it wrongly bounces.

    JEV_DATASET=dev     uv run python evals/jev/report_layer.py --tune     # writes thresholds.json
    JEV_DATASET=holdout uv run python evals/jev/report_layer.py            # uses saved thresholds
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from common import DATASET, LABELS, RESULTS, TRACES, read_jsonl
from questions_reject import JEV_REASONS, REASONS, reject_decision
from state import build_states

THRESHOLDS = Path(__file__).with_name("thresholds.json")
TARGET_PRECISION = 0.9
MIN_FIRES = 4
DEEPSEEK_REVIEW_USD = 0.00955
JEV_IN = 0.042e-6

# Rough map from a reason to words humans use for it (for "same reason?" agreement only).
HUMAN_WORDS = {
    "ai_code": r"\bai\b|vibe|30%|generated",
    "ai_readme": r"readme.*\bai\b|\bai\b.*readme",
    "readme_thin": r"readme.*(detail|more|incomplete|plain|minimal|nothing|expand|information)",
    "readme_not_raw": r"\braw\b",
    "no_readme": r"readme",
    "bad_hosting": r"railway|render|streamlit|ngrok|sleep",
    "demo_not_testable": r"demo|link|itch|crx|executable|download|release|channel|ship",
    "demo_broken": r"load|work|broken|error|demo",
    "feedback_ignored": r"previous|again|requested|reshipping|before|last reviewer",
    "ai_undeclared": r"declar",
    "not_eligible": r"school|eligib",
}


def load():
    labels = {r["cert_id"]: r for r in read_jsonl(LABELS)
              if r.get("human_verdict") in ("APPROVED", "REJECTED")}
    traces = {t["trace_id"]: t for t in read_jsonl(TRACES) if t["cert_id"] in labels}
    results = {r["trace_id"]: r for r in read_jsonl(RESULTS)
               if r.get("arm") == "reject" and "error" not in r}
    ids = [i for i in traces if i in results]
    facts = {i: build_states(traces[i])["facts"] for i in ids}
    return labels, traces, results, ids, facts


def summarize(name, decisions, human):
    rejects = [i for i, d in decisions.items() if d == "REJECT"]
    correct = sum(human[i] == "REJECTED" for i in rejects)
    total_rej = sum(h == "REJECTED" for h in human.values())
    total_app = len(human) - total_rej
    wrong = len(rejects) - correct
    prec = correct / len(rejects) if rejects else float("nan")
    print(f"{name:34} rejects {len(rejects):>3}  precision {prec:>5.0%}  "
          f"human-rejects caught {correct:>3}/{total_rej} ({correct / total_rej:.0%})  "
          f"good projects bounced {wrong:>2}/{total_app}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tune", action="store_true")
    args = parser.parse_args()
    labels, traces, results, ids, facts = load()
    human = {i: labels[traces[i]["cert_id"]]["human_verdict"] for i in ids}
    print(f"dataset={DATASET}  n={len(ids)}  human mix={Counter(human.values())}\n")

    # Per-reason reliability curve (the thing we tune on dev).
    print("per-reason: fires / precision at each threshold")
    ts = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)
    print(f"{'reason':20}" + "".join(f"{t:>12}" for t in ts))
    chosen: dict[str, float] = {}
    for key in JEV_REASONS:
        row = f"{key:20}"
        for t in ts:
            fired = [i for i in ids if reject_decision(results[i]["answers"], facts[i], {key: t})[1]
                     and key in reject_decision(results[i]["answers"], facts[i], {key: t})[1]]
            ok = sum(human[i] == "REJECTED" for i in fired)
            row += f"{len(fired):>5} {ok / len(fired):>5.0%} " if fired else f"{'0':>5} {'-':>5} "
            if (args.tune and key not in chosen and len(fired) >= MIN_FIRES
                    and ok / len(fired) >= TARGET_PRECISION):
                chosen[key] = t
        print(row)
    if args.tune:
        THRESHOLDS.write_text(json.dumps(chosen, indent=2))
        print(f"\nchosen on {DATASET} (lowest threshold with ≥{TARGET_PRECISION:.0%} precision and "
              f"≥{MIN_FIRES} fires): {chosen} -> {THRESHOLDS.name}")
    thresholds = json.loads(THRESHOLDS.read_text()) if THRESHOLDS.exists() else {}

    print("\nfirst-layer outcomes (REJECT vs pass-to-human):")
    summarize("deepseek (REJECT verdicts)", {i: "REJECT" if traces[i]["verdict"] == "REJECT" else "PASS" for i in ids}, human)
    summarize("code rules only (no model)", {i: reject_decision(results[i]["answers"], facts[i], {})[0] for i in ids}, human)
    summarize("code + jev (dev-tuned)", {i: reject_decision(results[i]["answers"], facts[i], thresholds)[0] for i in ids}, human)
    conservative = json.loads(THRESHOLDS.with_name("thresholds_conservative.json").read_text())
    summarize("code + jev (conservative)", {i: reject_decision(results[i]["answers"], facts[i], conservative)[0] for i in ids}, human)
    for t in (0.8, 0.9, 0.95):
        summarize(f"code + jev (all reasons @ {t})",
                  {i: reject_decision(results[i]["answers"], facts[i], dict.fromkeys(JEV_REASONS, t))[0] for i in ids}, human)

    # Reason agreement + which reasons fire, for the tuned system.
    fired = Counter()
    agree = total = 0
    examples = []
    for i in ids:
        verdict, reasons = reject_decision(results[i]["answers"], facts[i], thresholds)
        if verdict != "REJECT":
            continue
        fired.update(reasons)
        comment = (labels[traces[i]["cert_id"]].get("human_comment") or "").lower()
        if human[i] == "REJECTED":
            total += 1
            hit = any(re.search(HUMAN_WORDS[r], comment) for r in reasons)
            agree += hit
            if len(examples) < 6:
                examples.append((reasons, hit, comment[:140].replace("\n", " ")))
        else:
            examples.append((reasons, "WRONG (human approved)", ""))
    print(f"\nreasons fired: {dict(fired)}")
    if total:
        print(f"same reason as the human (keyword match) on correct rejects: {agree}/{total} ({agree / total:.0%})")
    for r, hit, c in examples[:10]:
        print(f"  {r} · match={hit} · {c}")

    tokens = [results[i]["usage"].get("input_tokens") or 0 for i in ids]
    lat = sorted(results[i]["latency_s"] for i in ids)
    print(f"\ncost: jev ${sum(tokens) / len(tokens) * JEV_IN:.5f}/review (avg {sum(tokens) / len(tokens):.0f} tokens), "
          f"p50 {lat[len(lat) // 2]:.2f}s p90 {lat[int(len(lat) * 0.9)]:.2f}s · deepseek ~${DEEPSEEK_REVIEW_USD}/review, ~56s")
    print("fix text per reason:", {k: REASONS[k][:50] + "…" for k in list(thresholds)[:3]})


if __name__ == "__main__":
    main()
