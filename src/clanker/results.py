"""Persistent record of what Clanker decided for each cert.

One JSON file per cert in ``Settings.results_dir``. The browser extension reads these
through ``clanker.api``; human "Clanker was right/wrong" feedback is stored on the same
record and can be exported as JSONL for evals. Nothing here talks to the Dashboard.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field, computed_field

if TYPE_CHECKING:
    from clanker.review.runner import ReviewOutcome

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def is_valid_id(cert_id: str) -> bool:
    return bool(_SAFE_ID.match(cert_id))


class HumanFeedback(BaseModel):
    agreement: Literal["right", "wrong"]
    note: str = ""
    wrong_checks: list[str] = Field(default_factory=list)
    decided_at: str
    by_id: str | None = None
    by_name: str | None = None


class ResultRecord(BaseModel):
    cert_id: str
    project_name: str
    repo_url: str | None = None
    demo_url: str | None = None
    stardance_url: str | None = None
    verdict: str  # REJECT | APPROVE | NEEDS_HUMAN (first layer) or the agent's verdict
    summary: str = ""
    reasons: list[str] = Field(default_factory=list)
    reason_labels: list[str] = Field(default_factory=list)  # human text, parallel to `reasons`
    message: str | None = None  # copy-ready text for the shipper (REJECT)
    video_path: str | None = None
    pdf_path: str | None = None
    created_at: str
    feedback: HumanFeedback | None = None
    requested_by: str | None = None  # who asked for this review from the extension
    slack_ts: str | None = None  # thread the review was announced in (for manual-review flags)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def manual_review(self) -> bool:
        """A human said Clanker got this one wrong: it needs a manual review."""
        return self.feedback is not None and self.feedback.agreement == "wrong"


def record_from_outcome(outcome: ReviewOutcome) -> ResultRecord:
    fl = outcome.first_layer
    cert = outcome.packet.cert
    if fl is not None:
        verdict, summary, reasons = fl.verdict, fl.summary, list(fl.reasons or fl.unsure)
    else:
        verdict = outcome.review.verdict.value
        summary = outcome.review.reasoning
        reasons = list(outcome.review.required_fixes or [])
    from clanker.review.first_layer.reviewer import REASON_LABELS

    return ResultRecord(
        cert_id=outcome.cert_id,
        project_name=cert.project_name,
        repo_url=cert.repo_url,
        demo_url=cert.demo_url,
        stardance_url=outcome.packet.stardance_url,
        verdict=verdict,
        summary=summary,
        reasons=reasons,
        reason_labels=[REASON_LABELS.get(r, r) for r in reasons],
        message=outcome.reject_message,
        video_path=str(outcome.video_path) if outcome.video_path else None,
        pdf_path=str(outcome.pdf_path) if outcome.pdf_path else None,
        created_at=datetime.now(UTC).isoformat(),
    )


class ResultStore:
    def __init__(self, directory: Path) -> None:
        self._dir = directory

    def _path(self, cert_id: str) -> Path:
        if not _SAFE_ID.match(cert_id):
            raise ValueError(f"invalid cert id: {cert_id!r}")
        return self._dir / f"{cert_id}.json"

    def _write(self, record: ResultRecord) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._path(record.cert_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(record.model_dump_json(indent=2))
        os.replace(tmp, path)

    def save_outcome(self, outcome: ReviewOutcome) -> ResultRecord:
        """Store a fresh result; keeps human feedback only if the new result is unchanged."""
        record = record_from_outcome(outcome)
        previous = self.get(record.cert_id)
        if (
            previous is not None
            and previous.verdict == record.verdict
            and previous.reasons == record.reasons
        ):
            record.feedback = previous.feedback
        if previous is not None:
            record.slack_ts = previous.slack_ts
        self._write(record)
        return record

    def get(self, cert_id: str) -> ResultRecord | None:
        path = self._path(cert_id)
        try:
            return ResultRecord.model_validate_json(path.read_text())
        except (FileNotFoundError, ValueError):
            return None

    def list(self, verdict: str | None = None) -> list[ResultRecord]:
        records = [
            r
            for p in self._dir.glob("*.json")
            if (r := self.get(p.stem)) is not None and (verdict is None or r.verdict == verdict)
        ]
        return sorted(records, key=lambda r: r.created_at, reverse=True)

    def set_feedback(
        self,
        cert_id: str,
        agreement: Literal["right", "wrong"],
        note: str = "",
        wrong_checks: list[str] | None = None,
        by: tuple[str, str] | None = None,
    ) -> ResultRecord:
        record = self.get(cert_id)
        if record is None:
            raise KeyError(cert_id)
        record.feedback = HumanFeedback(
            agreement=agreement,
            note=note.strip(),
            wrong_checks=wrong_checks or [],
            decided_at=datetime.now(UTC).isoformat(),
            by_id=by[0] if by else None,
            by_name=by[1] if by else None,
        )
        self._write(record)
        return record

    def clear_feedback(self, cert_id: str) -> ResultRecord:
        record = self.get(cert_id)
        if record is None:
            raise KeyError(cert_id)
        record.feedback = None
        self._write(record)
        return record

    def set_requested_by(self, cert_id: str, name: str) -> None:
        record = self.get(cert_id)
        if record is not None:
            record.requested_by = name
            self._write(record)

    def set_slack_ts(self, cert_id: str, ts: str) -> None:
        record = self.get(cert_id)
        if record is not None:
            record.slack_ts = ts
            self._write(record)

    def export_feedback_jsonl(self) -> str:
        """Every human-labelled result, one JSON object per line (for evals)."""
        return "".join(
            json.dumps(r.model_dump(mode="json"), ensure_ascii=False) + "\n"
            for r in reversed(self.list())
            if r.feedback is not None
        )
