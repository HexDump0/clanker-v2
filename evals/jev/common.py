"""Shared paths and helpers for the Jev decision eval (offline experiment, not app code)."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
# JEV_DATASET selects the split: "dev" (tuning) or "holdout" (reported once, never tuned on).
DATASET = os.environ.get("JEV_DATASET", "dev")
DATA = ROOT / "data" / "eval" / "jev" / DATASET
TRACES = DATA / "traces.jsonl"
LABELS = DATA / "labels.jsonl"
RESULTS = DATA / "results.jsonl"
CODE = DATA / "code.jsonl"

REVIEW_MARKER = "Shipwright Reviewer Agent"
JEV_MODEL = "~typesafe/jev-latest"
OPENROUTER_TYPESAFE_BASE = "https://openrouter.ai/api"


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    if not path.exists():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
