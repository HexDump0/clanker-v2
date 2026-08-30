"""Typed async client for the Shipwrights Dashboard API (ds.shipwrights.dev).

Reference: AI/context/API.md (reverse-engineered).
"""

from clanker.shipwrights.client import (
    AuthenticationError,
    CloudflareBlockError,
    MutationNotAllowedError,
    NotFoundError,
    ShipwrightsClient,
    ShipwrightsError,
)
from clanker.shipwrights.models import (
    CertDetail,
    CertificationAttempt,
    CertificationPage,
    CertStatus,
    CertSummary,
    FeedbackTemplate,
    FeedbackTemplates,
    GitHubCommit,
    GitHubData,
    GitHubRepo,
    ReadmeData,
    Review,
    Verdict,
)

__all__ = [
    "AuthenticationError",
    "CloudflareBlockError",
    "CertDetail",
    "CertificationAttempt",
    "CertificationPage",
    "CertStatus",
    "CertSummary",
    "FeedbackTemplate",
    "FeedbackTemplates",
    "GitHubCommit",
    "GitHubData",
    "GitHubRepo",
    "ReadmeData",
    "MutationNotAllowedError",
    "NotFoundError",
    "Review",
    "ShipwrightsClient",
    "ShipwrightsError",
    "Verdict",
]
