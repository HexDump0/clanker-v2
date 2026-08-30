from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from clanker.daily import (
    DailyStats,
    build_daily_summary,
    daily_fallback_text,
    gather_daily_stats,
    parse_daily_time,
    seconds_until_utc_time,
)
from clanker.shipwrights import CertSummary, LeaderboardEntry
from clanker.slack.announcer import Announcer
from tests.conftest import make_cert


def _cert_at(cert_id: str, created: datetime, **overrides) -> dict:
    return make_cert(
        cert_id,
        createdAt=created.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        **overrides,
    )


def _queue(dashboard, now: datetime) -> None:
    """Three certs older than 5d, two newer, ordered oldest-first (date:asc)."""
    certs = [
        _cert_at("old1", now - timedelta(days=9)),
        _cert_at("old2", now - timedelta(days=7)),
        _cert_at("old3", now - timedelta(days=6)),
        _cert_at("new1", now - timedelta(days=1)),
        _cert_at("new2", now - timedelta(hours=3)),
    ]
    dashboard.set_pending(certs)


async def test_gather_daily_stats(client, dashboard):
    now = datetime.now(UTC)
    _queue(dashboard, now)
    dashboard.leaderboard = {
        "entries": [
            {"memberId": "s:U092KBRD5SB", "name": "Utkrishth", "total": 11,
             "approved": 0, "rejected": 11},
            {"memberId": "s:U07950S3GMC", "name": "Shuflduf", "total": 7,
             "approved": 3, "rejected": 4},
        ]
    }

    stats = await gather_daily_stats(client)

    assert stats.pending == 5
    assert stats.era5 == 3
    assert stats.reviewed_today == 18
    assert [c.id for c in stats.oldest] == ["old1", "old2", "old3"]
    assert stats.best is not None
    assert stats.best.name == "Utkrishth"
    assert stats.praise is None  # praise is filled by build_daily_summary only


async def test_era5_walks_multiple_pages(client, dashboard):
    now = datetime.now(UTC)
    certs = [_cert_at(f"old{i:02}", now - timedelta(days=30)) for i in range(60)]
    certs += [_cert_at(f"new{i:02}", now - timedelta(hours=1)) for i in range(5)]
    dashboard.set_pending(certs)  # 65 certs -> 2 pages of ~50

    stats = await gather_daily_stats(client)

    assert stats.pending == 65
    assert stats.era5 == 60


def test_parse_daily_time():
    assert parse_daily_time("23:30") == (23, 30)
    assert parse_daily_time(" 0:05 ") == (0, 5)
    for bad in ("24:00", "12:60", "noon", "2330", ""):
        try:
            parse_daily_time(bad)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {bad!r}")


def test_seconds_until_utc_time():
    now = datetime(2026, 8, 30, 22, 0, tzinfo=UTC)
    assert seconds_until_utc_time(23, 30, now) == 90 * 60
    # 23:30 already passed today -> tomorrow
    later = datetime(2026, 8, 30, 23, 31, tzinfo=UTC)
    assert seconds_until_utc_time(23, 30, later) == 23 * 3600 + 59 * 60


def make_daily_announcer(daily_ping: str = "S123") -> tuple[Announcer, AsyncMock]:
    slack = AsyncMock()
    announcer = Announcer(
        slack,
        channel="C123",
        dashboard_base_url="https://ds.shipwrights.dev",
        workplace="stardance",
        daily_ping=daily_ping,
    )
    return announcer, slack


def _sample_stats(**overrides) -> DailyStats:
    certs = [
        make_cert("old1"),
        make_cert("old2", projectType="CLI"),
        make_cert("old3"),
    ]
    stats = DailyStats(
        pending=7,
        era5=3,
        reviewed_today=11,
        oldest=[CertSummary.model_validate(c) for c in certs],
    )
    stats.best = None
    if not overrides.get("no_best"):
        stats.best = LeaderboardEntry.model_validate(
            {"memberId": "s:U092KBRD5SB", "name": "Utkrishth", "total": 11}
        )
    stats.praise = overrides.get("praise", "You were almost tolerable today, meatbag.")
    return stats


async def test_announce_daily_summary_embed():
    announcer, slack = make_daily_announcer()
    await announcer.announce_daily_summary(_sample_stats())

    slack.chat_postMessage.assert_awaited_once()
    kwargs = slack.chat_postMessage.call_args.kwargs
    blob = json.dumps(kwargs["attachments"])
    assert "Daily Queue Stats" in blob
    assert "Hello meatbags :hello:" in blob
    assert "- 7 projects currently pending." in blob
    assert "- 3 projects have entered the 5d era." in blob
    assert "- 11 projects reviewed today." in blob
    # oldest three, linked, with ai/project type
    assert "ds.shipwrights.dev/stardance/certifications/old1" in blob
    assert "(Web App)" in blob and "(CLI)" in blob
    # best reviewer ping + praise + cc
    assert "<@U092KBRD5SB>" in blob
    assert ":yay2:" in blob
    assert "almost tolerable" in blob
    assert "cc: &lt;!subteam^S123&gt;" not in blob  # not escaped
    assert "<!subteam^S123>" in blob


async def test_announce_daily_summary_empty_queue_and_no_best():
    announcer, slack = make_daily_announcer(daily_ping="")
    stats = _sample_stats(no_best=True, praise=None)
    stats.oldest = []
    stats.pending = 0
    stats.era5 = 0
    stats.reviewed_today = 0
    await announcer.announce_daily_summary(stats)

    blob = json.dumps(slack.chat_postMessage.call_args.kwargs["attachments"])
    assert "queue is empty" in blob
    assert "yay2" not in blob
    assert "cc:" not in blob


async def test_build_daily_summary_fills_praise(client, dashboard, monkeypatch):
    now = datetime.now(UTC)
    _queue(dashboard, now)
    dashboard.leaderboard = {
        "entries": [{"memberId": "s:U092KBRD5SB", "name": "Utkrishth", "total": 11}]
    }

    async def fake_praise(settings, stats):
        return "generated line"

    monkeypatch.setattr("clanker.daily.generate_praise", fake_praise)
    stats = await build_daily_summary(client, settings=object())
    assert stats.praise == "generated line"


async def test_build_daily_summary_praise_failure_uses_fallback(client, dashboard, monkeypatch):
    now = datetime.now(UTC)
    _queue(dashboard, now)
    dashboard.leaderboard = {
        "entries": [{"memberId": "s:U092KBRD5SB", "name": "Utkrishth", "total": 11}]
    }

    async def boom(settings, stats):
        raise RuntimeError("no key")

    monkeypatch.setattr("clanker.daily.generate_praise", boom)
    stats = await build_daily_summary(client, settings=object())
    assert stats.praise  # one of the canned fallbacks


def test_fallback_text():
    text = daily_fallback_text(_sample_stats())
    assert "7 projects currently pending." in text
    assert "Project old1 (Web App)" in text
    assert "Utkrishth (11 reviews)" in text
