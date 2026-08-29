"""Score a clanker-v2 benchmark run against human decisions.

Reads the JSONL produced by ``bench_reviews.py`` and reports accuracy, a
confusion matrix, and the costly-error rates.

FLAG_FOR_HUMAN scoring ("correct-if-safe", per the benchmark owner):
  - FLAG on a human-REJECT  -> counted CORRECT (the bot escalated a bad ship
    for review rather than approving it).
  - FLAG on a human-APPROVE -> counted WRONG (needless friction on a good ship).

Usage:
  uv run python scripts/score_bench.py [--in data/bench/results.jsonl] [--errors]
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

DEFAULT_IN = Path("data/bench/results.jsonl")
VERDICTS = ("APPROVE", "REJECT", "FLAG_FOR_HUMAN")
TRUTHS = ("APPROVE", "REJECT")


def is_correct(truth: str, predicted: str) -> bool:
    if predicted == truth:
        return True
    if predicted == "FLAG_FOR_HUMAN":
        return truth == "REJECT"  # correct-if-safe
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="inp", type=Path, default=DEFAULT_IN)
    parser.add_argument("--errors", action="store_true", help="list disagreements + errors")
    args = parser.parse_args()

    scored: list[dict] = []
    errors: list[dict] = []
    with args.inp.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("predicted") and rec.get("truth"):
                scored.append(rec)
            else:
                errors.append(rec)

    total = len(scored)
    if not total:
        print("No scored records found.")
        return

    correct = sum(1 for r in scored if is_correct(r["truth"], r["predicted"]))
    # Confusion matrix: truth (rows) x predicted (cols)
    matrix: Counter[tuple[str, str]] = Counter(
        (r["truth"], r["predicted"]) for r in scored
    )

    print(f"Scored: {total} certs  |  Errors/unscored: {len(errors)}")
    print(f"Overall accuracy (correct-if-safe): {correct}/{total} = {correct / total:.1%}\n")

    # ---- confusion matrix ----
    col_w = max(len(v) for v in VERDICTS) + 2
    header = "truth \\ pred".ljust(14) + "".join(v.ljust(col_w) for v in VERDICTS)
    print(header)
    for t in TRUTHS:
        row = t.ljust(14) + "".join(
            str(matrix.get((t, p), 0)).ljust(col_w) for p in VERDICTS
        )
        print(row)
    print()

    # ---- costly error rates ----
    n_approve = sum(1 for r in scored if r["truth"] == "APPROVE")
    n_reject = sum(1 for r in scored if r["truth"] == "REJECT")

    false_approve = matrix.get(("REJECT", "APPROVE"), 0)   # approved a bad ship
    false_reject = matrix.get(("APPROVE", "REJECT"), 0)    # rejected a good ship
    flag_on_good = matrix.get(("APPROVE", "FLAG_FOR_HUMAN"), 0)
    flag_on_bad = matrix.get(("REJECT", "FLAG_FOR_HUMAN"), 0)
    flags = flag_on_good + flag_on_bad

    def pct(n: int, d: int) -> str:
        return f"{n}/{d} = {n / d:.1%}" if d else f"{n}/0"

    print("Human APPROVE certs:", n_approve, "| Human REJECT certs:", n_reject)
    print(f"  FALSE APPROVE (bot APPROVE on human REJECT): {pct(false_approve, n_reject)} <-costly")
    print(f"  FALSE REJECT  (bot REJECT on human APPROVE): {pct(false_reject, n_approve)} <-friction")
    print(f"  Correct APPROVE: {pct(matrix.get(('APPROVE','APPROVE'),0), n_approve)}")
    print(f"  Correct REJECT : {pct(matrix.get(('REJECT','REJECT'),0), n_reject)}")
    print(f"  Flags total: {pct(flags, total)}  (on good: {flag_on_good}, on bad: {flag_on_bad})")

    # ---- precision/recall for REJECT (catching bad ships) ----
    tp = matrix.get(("REJECT", "REJECT"), 0)
    fp = matrix.get(("APPROVE", "REJECT"), 0)
    fn = matrix.get(("REJECT", "APPROVE"), 0)
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    print(f"\nREJECT precision: {prec:.1%} | recall: {rec:.1%} "
          "(decisive verdicts only; flags excluded)")

    # ---- token/latency summary ----
    toks_in = sum(r.get("input_tokens", 0) for r in scored)
    toks_out = sum(r.get("output_tokens", 0) for r in scored)
    elapsed = [r.get("elapsed_s", 0) for r in scored if r.get("elapsed_s")]
    if elapsed:
        print(
            f"\nTokens: {toks_in:,} in / {toks_out:,} out"
            f" | median latency {sorted(elapsed)[len(elapsed)//2]:.0f}s"
        )

    if args.errors:
        print("\n--- Disagreements ---")
        for r in scored:
            if not is_correct(r["truth"], r["predicted"]):
                print(
                    f"  {r['id']}  truth={r['truth']} pred={r['predicted']}  "
                    f"{r.get('project_name','')!r}"
                )
                reasoning = (r.get("review") or {}).get("reasoning", "")
                print(f"      {reasoning[:200]}")
        if errors:
            print("\n--- Errors / unscored ---")
            for r in errors:
                print(f"  {r.get('id')}  {r.get('error', 'no prediction')}")


if __name__ == "__main__":
    main()
