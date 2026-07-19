"""Typed async client for the Shipwrights Dashboard API (ds.shipwrights.dev).

Reference: AI/context/API.md (reverse-engineered).
"""

from clanker.shipwrights.client import (
    AuthenticationError,
    MutationNotAllowedError,
    NotFoundError,
    ShipwrightsClient,
    ShipwrightsError,
)
from clanker.shipwrights.models import (
    CertDetail,
    CertificationPage,
    CertStatus,
    CertSummary,
    GitHubCommit,
    GitHubData,
    GitHubRepo,
    Review,
    Verdict,
)

__all__ = [
    "AuthenticationError",
    "CertDetail",
    "CertificationPage",
    "CertStatus",
    "CertSummary",
    "GitHubCommit",
    "GitHubData",
    "GitHubRepo",
    "MutationNotAllowedError",
    "NotFoundError",
    "Review",
    "ShipwrightsClient",
    "ShipwrightsError",
    "Verdict",
]
