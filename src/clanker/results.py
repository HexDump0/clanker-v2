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
_SHIP_URL = re.compile(r"/ship/(\d+)")
# Stardance spells a negative review "returned"; there is no "rejected" outcome in its review
# log. Both mean a human has finished with the ship, so both close it out of the Clanker
# queue. See `clanker.status` for how these are read.
DECISIONS = frozenset({"approved", "returned"})


def is_valid_id(cert_id: str) -> bool:
    return bool(_SAFE_ID.match(cert_id))


def ship_id_of(stardance_url: str | None) -> str | None:
    """The Stardance ship number (``#15895`` -> ``"15895"``) from a stored ship URL."""
    match = _SHIP_URL.search(stardance_url or "")
    return match.group(1) if match else None


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
    # What a human has since done with this ship, read from Stardance's review log by
    # `clanker.status`. All None until the first pass, which is treated as "not decided", so
    # nothing drops out of the queue before the refresher has run.
    decision: str | None = None  # "approved" | "returned" | None (no review yet)
    reviewed_by: str | None = None  # the reviewer's Stardance name
    reviewed_at: str | None = None  # approximate ISO; the page only prints "3 minutes ago"
    review_note: str | None = None  # the human's feedback text (truncated on the page)
    waiting: bool | None = None  # back in the Stardance queue (a resubmission)
    checked_at: str | None = None  # when we last read this ship's state

    @computed_field  # type: ignore[prop-decorator]
    @property
    def manual_review(self) -> bool:
        """A human said Clanker got this one wrong: it needs a manual review."""
        return self.feedback is not None and self.feedback.agreement == "wrong"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def in_queue(self) -> bool:
        """Still waiting on a human: not marked wrong, and no human has decided it yet.

        Clanker's own verdict (reject / approve / needs human) never takes a ship off the
        queue. A ship stays in while Stardance still lists it as waiting — that is how a
        resubmission after a "returned" comes back on its own — and leaves once a review
        log entry exists and it is no longer waiting.
        """
        if self.manual_review:
            return False
        if self.waiting:
            return True
        return self.decision is None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def auto_agreement(self) -> str | None:
        """"right" / "wrong" inferred from the human's decision, or None when unknowable.

        Never stored and never overwrites an explicit human label — this is what the data
        already says, not what somebody claimed. See `infer_agreement` for the rules.
        """
        return infer_agreement(self)[0]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def auto_reason(self) -> str:
        """One line saying why `auto_agreement` came out the way it did ("" when unknown)."""
        return infer_agreement(self)[1]


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


# What a human's action means for a ship Clanker judged. Clanker said REJECT and the reviewer
# sent it back is agreement; the reverse is disagreement. Clanker NEEDS HUMAN is not a claim
# about the ship either way, so a human bouncing it is not a correction of Clanker.
_AGREEMENT = {
    ("REJECT", "returned"): "right",
    ("APPROVE", "approved"): "right",
    ("REJECT", "approved"): "wrong",
    ("APPROVE", "returned"): "wrong",
}


def infer_agreement(record: ResultRecord) -> tuple[str | None, str]:
    """Work out whether a human agreed with Clanker, and say why.

    Returns ``(None, "")`` whenever the comparison would be unfair or meaningless:

    - a human already labelled this ship themselves (their word wins, and the ship is flagged);
    - nobody has reviewed it yet;
    - the human's review is *older* than Clanker's. Stardance's review log keeps one row per
      ship — its most recent review (verified 2026-10-02: 500 rows, 500 distinct ships, and
      ships whose own feedback says "again as mentioned before" still appear once) — so after a
      resubmission the logged action can be from the previous attempt, and comparing it to a
      later Clanker run would score a ship Clanker never actually saw.
    """
    if record.manual_review:
        return None, ""
    if record.decision not in ("approved", "returned"):
        return None, ""
    human_at, clanker_at = _parse_iso(record.reviewed_at), _parse_iso(record.created_at)
    if human_at is not None and clanker_at is not None and human_at < clanker_at:
        return None, ""

    who = f" by {record.reviewed_by}" if record.reviewed_by else ""
    said = {
        "REJECT": "Clanker said reject",
        "APPROVE": "Clanker said approve",
    }.get(record.verdict)
    if said is None:
        # NEEDS HUMAN, or an agent-path verdict we do not score.
        return None, "" if record.verdict == "NEEDS_HUMAN" else f"unscored verdict {record.verdict}"
    did = "a reviewer returned it" if record.decision == "returned" else "a reviewer approved it"
    agreement = _AGREEMENT.get((record.verdict, record.decision))
    if agreement is None:
        return None, f"{said}, {did}{who}"
    return agreement, f"{said}; {did}{who}"


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
        if previous is not None:
            record.slack_ts = previous.slack_ts
            # What a human did with the ship outlives our judgement of it: without this a
            # re-review would drop a decided ship back into the Clanker queue.
            record.decision = previous.decision
            record.reviewed_by = previous.reviewed_by
            record.reviewed_at = previous.reviewed_at
            record.review_note = previous.review_note
            record.waiting = previous.waiting
            record.checked_at = previous.checked_at
            if previous.verdict == record.verdict and previous.reasons == record.reasons:
                record.feedback = previous.feedback
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

    def set_review_state(
        self,
        cert_id: str,
        *,
        decision: str | None,
        waiting: bool,
        reviewed_by: str | None = None,
        reviewed_at: str | None = None,
        review_note: str | None = None,
    ) -> ResultRecord | None:
        """Record what a human has done with a ship, as read from Stardance's review log.

        Skips the write when nothing changed. Read-modify-write is synchronous, so it cannot
        interleave with another store write in the same event loop (feedback, thread or
        review state) and lose an update.
        """
        record = self.get(cert_id)
        if record is None:
            return None
        unchanged = (
            record.decision == decision
            and record.waiting == waiting
            and record.reviewed_by == reviewed_by
            and record.review_note == review_note
            and (reviewed_at is None or record.reviewed_at == reviewed_at)
        )
        if unchanged:
            # Still record that we looked, so "checked 2m ago" stays honest.
            record.checked_at = datetime.now(UTC).isoformat()
            self._write(record)
            return record
        record.decision = decision
        record.waiting = waiting
        record.reviewed_by = reviewed_by
        record.reviewed_at = reviewed_at or record.reviewed_at
        record.review_note = review_note
        record.checked_at = datetime.now(UTC).isoformat()
        self._write(record)
        return record

    def export_feedback_jsonl(self) -> str:
        """Every human-labelled result, one JSON object per line (for evals)."""
        return "".join(
            json.dumps(r.model_dump(mode="json"), ensure_ascii=False) + "\n"
            for r in reversed(self.list())
            if r.feedback is not None
        )
