"""First-layer reject rules for the eval harness: re-exported from production.

The source of truth is ``clanker.review.first_layer.rules``, so evaluations measure exactly
what the live bot runs.
"""

from clanker.review.first_layer.rules import (  # noqa: F401
    AI_LOOK,
    BAD_BANNERS,
    BOT_HOSTS,
    BUILD_EXT,
    DEFAULT_THRESHOLDS,
    ITCH_PLAYABLE,
    JEV_REASONS,
    REASONS,
    VIDEO_HOSTS,
    build_reject_questions,
    code_rules,
    reject_decision,
)
