"""Pydantic models for Shipwrights Dashboard API responses.

Field names mirror the API's camelCase via an alias generator; unknown fields are
kept (``extra="allow"``) so nothing the server sends is silently dropped.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CertStatus(StrEnum):
    PENDING = "PENDING"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RETURNED = "RETURNED"


class Verdict(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class _ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="allow",
    )


class Reviewer(_ApiModel):
    slack_id: str | None = None
    display_name: str | None = None
    slack_username: str | None = None
    slack_avatar: str | None = None


class Review(_ApiModel):
    # Historical attempt reviews omit id/certId in the current API.
    id: str | None = None
    cert_id: str | None = None
    reviewer_id: str | None = None
    reviewer_slack_id: str | None = None
    verdict: Verdict
    comment: str | None = None
    created_at: datetime
    reviewer: Reviewer | None = None


class ReviewCount(_ApiModel):
    reviews: int = 0


class Claimer(_ApiModel):
    id: str | None = None
    slack_id: str | None = None
    display_name: str | None = None
    slack_username: str | None = None
    slack_avatar: str | None = None


class CertificationAttempt(_ApiModel):
    """One submission attempt in a certification's full review history."""

    id: str
    external_id: str | None = None
    project_name: str | None = None
    status: CertStatus
    created_at: datetime | None = None
    return_reason: str | None = None
    returned_at: datetime | None = None
    reviews: list[Review] = Field(default_factory=list)


class CertSummary(_ApiModel):
    id: str
    workplace_id: str | None = None
    external_id: str | None = None
    idempotency_key: str | None = None
    submitter_slack_id: str | None = None
    submitter_username: str | None = None
    submitter_name: str | None = None
    project_name: str
    project_type: str | None = None
    ship_type: str | None = None
    description: str | None = None
    ai_declaration: str | None = None
    ai_type: str | None = None
    # Parsed for schema compatibility but excluded from dumps and never passed
    # to Clanker's agents; the review must remain independent.
    ai_summary: str | None = Field(default=None, exclude=True, repr=False)
    ai_index_state: str | None = None
    ai_index_error: str | None = None
    ai_indexed_at: datetime | None = None
    updated_project: str | None = None
    demo_url: str | None = None
    repo_url: str | None = None
    readme_url: str | None = None
    dev_time: str | None = None
    status: CertStatus
    claimer_id: str | None = None
    claimed_at: datetime | None = None
    claimer: Claimer | None = None
    internal_notes: str | None = None
    proof_video_url: str | None = None
    hackatime_projects: list[str] = Field(default_factory=list)
    return_reason: str | None = None
    returned_at: datetime | None = None
    ysws_picked_up: bool | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    count: ReviewCount | None = Field(default=None, alias="_count")


class CertDetail(CertSummary):
    submitter_avatar: str | None = None
    reviews: list[Review] = Field(default_factory=list)
    attempts: list[CertificationAttempt] = Field(default_factory=list)
    active_events: list[dict[str, Any]] = Field(default_factory=list)
    feedback_required: bool | None = None
    proof_video_required: bool | None = None
    feedback_templates_enabled: bool | None = None
    viewer_is_claimer: bool | None = None
    viewer_is_global_admin: bool | None = None
    ai_enabled: bool | None = None
    can_report: bool | None = None


class OldestCert(_ApiModel):
    id: str
    age_secs: float | None = None


class CertificationPage(_ApiModel):
    certs: list[CertSummary] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    pages: int = 1
    can_import: bool | None = None
    stats: dict[str, int] = Field(default_factory=dict)
    avg_wait: float | None = None
    oldest: OldestCert | None = None
    ai_enabled: bool | None = None
    ai_types: list[str] = Field(default_factory=list)
    ai_type_counts: dict[str, int] = Field(default_factory=dict)


class GitHubRepo(_ApiModel):
    full_name: str | None = None
    url: str | None = None
    created_at: datetime | None = None
    language: str | None = None


class GitHubCommit(_ApiModel):
    sha: str | None = None
    short_sha: str | None = None
    message: str | None = None
    author_name: str | None = None
    author_login: str | None = None
    date: datetime | None = None
    url: str | None = None


class GitHubData(_ApiModel):
    repo: GitHubRepo | None = None
    commits: list[GitHubCommit] = Field(default_factory=list)
    fetched_at: datetime | None = None
    status: str | None = None
    cached: bool | None = None


class ReadmeData(_ApiModel):
    status: str | None = None
    cached: bool | None = None
    markdown: str = ""
    fetched_at: datetime | None = None
    error: str | None = None


class FeedbackTemplate(_ApiModel):
    id: str
    title: str
    body: str
    shared: bool | None = None


class FeedbackTemplates(_ApiModel):
    shared: list[FeedbackTemplate] = Field(default_factory=list)
    mine: list[FeedbackTemplate] = Field(default_factory=list)
    reviewer_slack_username: str | None = None


class LeaderboardEntry(_ApiModel):
    member_id: str
    name: str | None = None
    avatar: str | None = None
    total: int = 0
    approved: int = 0
    rejected: int = 0
