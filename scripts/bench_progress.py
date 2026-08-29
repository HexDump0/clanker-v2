"""Live progress bar for a running bench_reviews.py run.

Polls the results JSONL and renders a terminal progress bar in place.

  uv run python scripts/bench_progress.py
  uv run python scripts/bench_progress.py --interval 2 --out data/bench/results.jsonl
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path


def snapshot(out: Path, total: int) -> tuple[int, int, Counter]:
    """(done, unresolvable, error-type counts) from the latest state per cert id."""
    by_id: dict[str, dict] = {}
    if out.exists():
        with out.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                i = str(rec.get("id"))
                # A prediction is terminal; otherwise keep the first-seen error.
                if rec.get("predicted"):
                    by_id[i] = rec
                elif i not in by_id:
                    by_id[i] = rec
    done = sum(1 for r in by_id.values() if r.get("predicted"))
    unres = sum(
        1
        for r in by_id.values()
        if not r.get("predicted")
        and str(r.get("error", "")).startswith("could not resolve")
    )
    errs = Counter(
        str(r.get("error", "?")).split(":")[0]
        for r in by_id.values()
        if not r.get("predicted")
    )
    return done, unres, errs


def bar(frac: float, width: int = 40) -> str:
    filled = int(frac * width)
    return "█" * filled + "░" * (width - filled)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("data/bench/results.jsonl"))
    ap.add_argument("--csv", type=Path, default=Path("data/bench/500-recently-reviewed-certs.csv"))
    ap.add_argument("--interval", type=float, default=3.0, help="refresh seconds")
    args = ap.parse_args()

    with args.csv.open(encoding="utf-8") as fh:
        total = sum(1 for _ in csv.DictReader(fh))

    start = time.monotonic()
    start_done: int | None = None
    try:
        while True:
            done, unres, errs = snapshot(args.out, total)
            settled = done + unres
            if start_done is None:
                start_done = done
            elapsed = time.monotonic() - start
            rate = (done - start_done) / elapsed * 60 if elapsed > 0 else 0  # per min
            remaining = total - settled
            eta = f"{remaining / rate:.0f}m" if rate > 0.1 else "—"
            frac = settled / total if total else 0
            errtxt = " ".join(f"{k}={v}" for k, v in errs.most_common(3)) or "none"
            sys.stdout.write(
                f"\r{bar(frac)} {settled}/{total} "
                f"({frac:.0%}) | done {done} unres {unres} | "
                f"{rate:.1f}/min ETA {eta} | err: {errtxt}   "
            )
            sys.stdout.flush()
            if settled >= total:
                sys.stdout.write("\n✅ complete\n")
                return
            time.sleep(args.interval)
    except KeyboardInterrupt:
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
