"""Structured output models for the review agent.

Unlike v1 (where equivalent models existed but were never wired up), the agent
runs with ``output_type=ReviewOutput`` — the verdict is validated data, never
scraped out of the message log.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class CheckStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"


class ReviewVerdict(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    FLAG_FOR_HUMAN = "FLAG_FOR_HUMAN"


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
