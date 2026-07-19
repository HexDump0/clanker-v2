"""Structured output models for the review agent.

Unlike v1 (where equivalent models existed but were never wired up), the agent
uses ``PromptedOutput(ReviewOutput)`` — the verdict is validated data, never
scraped out of the message log or represented as a forced output-tool call.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CheckStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"


class ReviewVerdict(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    FLAG_FOR_HUMAN = "FLAG_FOR_HUMAN"


class VideoEvidence(BaseModel):
    """A browser-visible finding that may become a video scene.

    The review agent owns the finding and URL. It deliberately does not choose a
    selector, text anchor, rectangle, or screenshot treatment; those belong to
    the separate video pipeline.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,47}$")
    check: str = Field(description="Rubric check or short evidence category.")
    url: str = Field(description="Public HTTP(S) page on which the finding can be shown.")
    finding: str = Field(
        min_length=1,
        max_length=500,
        description="Factual finding already established by the review.",
    )
    fix_ids: list[int] = Field(
        default_factory=list,
        description="One-based indexes into required_fixes that this evidence supports.",
    )

    @field_validator("url")
    @classmethod
    def _http_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("video evidence URL must use HTTP(S)")
        return value

    @field_validator("fix_ids")
    @classmethod
    def _positive_unique_fix_ids(cls, value: list[int]) -> list[int]:
        if any(item < 1 for item in value):
            raise ValueError("fix_ids are one-based and must be positive")
        if len(value) != len(set(value)):
            raise ValueError("fix_ids must be unique")
        return value


class CheckResult(BaseModel):
    """A single check's outcome."""

    status: CheckStatus
    details: str = Field(
        default="", description="One or two sentences of evidence for the status."
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_bare_status(cls, value: Any) -> Any:
        # Lenient with weaker models: accept "pass" where {"status": "pass", ...}
        # is expected.
        if isinstance(value, str):
            return {"status": value}
        return value

    @field_validator("status", mode="before")
    @classmethod
    def _lowercase_status(cls, value: Any) -> Any:
        return value.lower() if isinstance(value, str) else value


class ChecksResult(BaseModel):
    """The full rubric. Every check must be evaluated (use status=skip if not applicable)."""

    @model_validator(mode="before")
    @classmethod
    def _parse_double_encoded_json(cls, value: Any) -> Any:
        # Some models emit the nested checks object as a JSON string.
        if isinstance(value, str):
            import json

            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value

    readme_is_raw_github: CheckResult
    readme_matches_repo: CheckResult
    repo_link_valid: CheckResult
    pre_event_commits: CheckResult
    ai_detection: CheckResult
    commit_authorship: CheckResult
    readme_boilerplate: CheckResult
    readme_substance: CheckResult
    readme_language: CheckResult
    demo_validity: CheckResult
    demo_credentials: CheckResult
    description_accuracy: CheckResult
    demo_link_type: CheckResult

    def as_pdf_rows(self) -> list[dict[str, str]]:
        """Rows for the Typst template: [{"name", "status", "details"}, ...]."""
        return [
            {"name": name, "status": check.status.value, "details": check.details}
            for name, check in self
        ]


class ReviewOutput(BaseModel):
    """Final structured result of one review run."""

    verdict: ReviewVerdict
    project_type: str = Field(
        description='Short detected type label, e.g. "Web App", "CLI Tool". No parentheticals.'
    )
    type_mismatch: bool = Field(
        default=False,
        description="True if the detected type differs from the submission's claimed type.",
    )
    instant_reject: bool = False
    instant_reject_reason: str | None = None
    checks: ChecksResult
    reasoning: str = Field(
        description="Cohesive paragraph referencing specific check results as evidence."
    )
    required_fixes: list[str] | None = Field(
        default=None, description="REJECT only: smallest set of changes needed for approval."
    )
    feedback: list[str] | None = Field(
        default=None, description="Short helpful suggestions, even when approving."
    )
    special_flags: list[str] | None = Field(
        default=None,
        description=(
            'e.g. "UPDATED PROJECT", "NEEDS HUMAN REVIEW (VR)", "AI UNDISCLOSED", '
            '"RESUBMISSION SPAM".'
        ),
    )
    video_evidence: list[VideoEvidence] = Field(
        default_factory=list,
        max_length=5,
        description=(
            "Material browser-visible evidence for an optional review video. Supply URLs and "
            "findings only; never selectors, highlight text, or coordinates."
        ),
    )

    @model_validator(mode="after")
    def _validate_video_evidence(self) -> ReviewOutput:
        ids = [item.id for item in self.video_evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("video_evidence ids must be unique")
        fix_count = len(self.required_fixes or [])
        if any(fix_id > fix_count for item in self.video_evidence for fix_id in item.fix_ids):
            raise ValueError("video evidence references a missing required fix")
        return self
