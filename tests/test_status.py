"""Ship review states: parsing Stardance's review log, and the refresher that fills them in."""

from __future__ import annotations

import httpx
import pytest

from clanker.config import Settings
from clanker.results import ResultRecord, ResultStore, ship_id_of
from clanker.stardance import (
    StardanceAdminClient,
    StardanceAdminError,
    parse_relative_when,
    parse_review_log,
)
from clanker.status import ReviewLogCache, StatusRefresher

# Trimmed from the live page (2026-10-02). The table rows are plain <tr>; the same ships are
# also rendered as <a class="ship-queue__card"> for narrow screens, which must be ignored.
REVIEW_LOG_HTML = """
<html><body>
<table class="ship-queue__table">
  <tr><th>Project</th><th>Feedback</th><th class="ship-queue__cell-status">Status</th></tr>
  <tr>
    <td class="ship-queue__cell-project">
      <div class="ship-queue__project-head">
        <a class="ship-queue__project-title" href="/admin/certification/ship/15895">Tic Tac Toe</a>
        <span class="ship-queue__project-id">#15895</span>
      </div>
      <div class="ship-queue__project-meta">
        <span>by Midhunesh</span>
        <span class="ship-queue__dot" aria-hidden="true">·</span>
        <span>reviewed by Floppy</span>
        <span class="ship-queue__dot" aria-hidden="true">·</span>
        <span>4 minutes ago</span>
      </div>
    </td>
    <td class="ship-queue__cell-feedback">Looks very much vibecoded, please rework it...</td>
    <td class="ship-queue__cell-status">
      <span class="status-pill status-pill--returned">Returned</span>
    </td>
  </tr>
  <tr>
    <td class="ship-queue__cell-project">
      <div class="ship-queue__project-head">
        <a class="ship-queue__project-title" href="/admin/certification/ship/15900">Portfolio</a>
        <span class="ship-queue__project-id">#15900</span>
      </div>
      <div class="ship-queue__project-meta">
        <span>by Archit</span>
        <span class="ship-queue__dot" aria-hidden="true">·</span>
        <span>reviewed by kaboom</span>
        <span class="ship-queue__dot" aria-hidden="true">·</span>
        <span>2 days ago</span>
      </div>
    </td>
    <td class="ship-queue__cell-feedback">Ship it!</td>
    <td class="ship-queue__cell-status">
      <span class="status-pill status-pill--approved">Approved</span>
    </td>
  </tr>
</table>
<div class="ship-queue__cards">
  <a class="ship-queue__card" href="/admin/certification/ship/15895">
    <span class="ship-queue__project-title">Tic Tac Toe</span>
    <span class="ship-queue__project-id">#15895</span>
    <span class="status-pill status-pill--returned">Returned</span>
  </a>
</div>
<div class="ship-queue__empty"><p>No reviewed ships match these filters.</p></div>
</body></html>
"""

QUEUE_HTML = """
<html><body>
<div class="ship-queue__metrics"><span class="ship-queue__label">In queue</span>
<span class="ship-queue__metric-value is-negative">
2
</span></div>
<table class="ship-queue__table">
  <tr><th>Ship</th></tr>
  <tr class="ship-queue__row ship-queue__row--link"><td class="ship-queue__cell-project">
    <span class="ship-queue__project-title">Waiting One</span>
    <span class="ship-queue__project-id">#16000</span>
  </td></tr>
  <tr class="ship-queue__row ship-queue__row--own"><td class="ship-queue__cell-project">
    <span class="ship-queue__project-title">Waiting Two</span>
    <span class="ship-queue__project-id">#16001</span>
  </td></tr>
</table>
</body></html>
"""


def test_parse_review_log_reads_every_field() -> None:
    entries = parse_review_log(REVIEW_LOG_HTML)
    assert [e.ship_id for e in entries] == ["15895", "15900"]
    first = entries[0]
    assert first.title == "Tic Tac Toe"
    assert first.author == "Midhunesh"
    assert first.reviewed_by == "Floppy"
    assert first.when_text == "4 minutes ago"
    assert first.decision == "returned"
    assert first.feedback.startswith("Looks very much vibecoded")
    assert entries[1].decision == "approved"


def test_cards_are_not_counted_twice() -> None:
    """The page renders every ship twice (table + responsive card); only the table counts."""
    assert len(parse_review_log(REVIEW_LOG_HTML)) == 2


def test_empty_review_log_is_not_an_error() -> None:
    assert parse_review_log("<html><body>no rows</body></html>") == []


def test_parse_relative_when() -> None:
    from datetime import UTC, datetime

    now = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    assert parse_relative_when("4 minutes ago", now=now) == "2026-10-02T11:56:00+00:00"
    assert parse_relative_when("2 days ago", now=now) == "2026-09-30T12:00:00+00:00"
    assert parse_relative_when("just now", now=now) is None
    assert parse_relative_when("", now=now) is None


# ---------------------------------------------------------------- store behaviour


def _record(cert_id: str = "c1", ship: str | None = "15895") -> ResultRecord:
    return ResultRecord(
        cert_id=cert_id,
        project_name="Proj",
        verdict="REJECT",
        stardance_url=f"https://stardance.hackclub.com/admin/certification/ship/{ship}"
        if ship
        else None,
        created_at="2026-10-01T00:00:00+00:00",
    )


def test_ship_id_of() -> None:
    assert ship_id_of("https://stardance.hackclub.com/admin/certification/ship/15814?via=x") == (
        "15814"
    )
    assert ship_id_of(None) is None
    assert ship_id_of("https://example.com/nope") is None


def test_queue_membership_follows_humans_not_clanker(tmp_path) -> None:
    store = ResultStore(tmp_path)
    store._write(_record("decided"))
    store._write(_record("waiting-again"))
    store._write(_record("untouched"))
    store._write(_record("flagged"))

    # A human approved it: out of the queue, whatever Clanker said.
    store.set_review_state("decided", decision="approved", waiting=False)
    # Returned, then the shipper resubmitted it: back in the queue.
    store.set_review_state("waiting-again", decision="returned", waiting=True)
    # Nobody has looked at it yet: still waiting on a human.
    store.set_review_state("untouched", decision=None, waiting=False)
    store.set_feedback("flagged", "wrong", note="readme exists")

    records = {r.cert_id: r for r in store.list()}
    assert records["decided"].in_queue is False
    assert records["waiting-again"].in_queue is True
    assert records["untouched"].in_queue is True
    assert records["flagged"].in_queue is False  # marked wrong


def test_a_decided_ship_leaves_before_any_refresh(tmp_path) -> None:
    """An untouched record must not look decided, or ships vanish on upgrade."""
    assert _record().in_queue is True
    assert _record().decision is None


def test_set_review_state_records_the_reviewer_and_feedback(tmp_path) -> None:
    store = ResultStore(tmp_path)
    store._write(_record())
    store.set_review_state(
        "c1",
        decision="returned",
        waiting=False,
        reviewed_by="frog",
        review_note="more than 30% AI",
    )
    record = store.get("c1")
    assert (record.reviewed_by, record.review_note, record.waiting) == (
        "frog",
        "more than 30% AI",
        False,
    )
    assert record.checked_at is not None


def test_set_review_state_on_a_missing_record(tmp_path) -> None:
    store = ResultStore(tmp_path)
    assert store.set_review_state("nope", decision="approved", waiting=False) is None


# ---------------------------------------------------------------- refresher


class FakeAdmin:
    """Stands in for StardanceAdminClient: a waiting set plus a review log.

    ``log`` is the whole log. ``page1`` caps how many rows the newest page holds, so a test can
    make the log longer than one page and exercise the cache's page-following.
    """

    def __init__(
        self,
        waiting: set[str],
        log: dict[str, tuple[str, str, str]],
        *,
        page1: int | None = None,
    ) -> None:
        self.waiting = waiting
        self.log = log  # ship id -> (decision, reviewer, feedback)
        self.page1 = len(log) if page1 is None else page1
        self.calls: list[dict[str, str]] = []

    def _rows(self, page: int, limit: int) -> list:
        ids = sorted(self.log, key=int, reverse=True)
        window = min(limit, self.page1) if page == 1 else limit
        start = (page - 1) * limit
        return [
            _entry(ship_id, "A Project", "someone", *self.log[ship_id])
            for ship_id in ids[start : start + window]
        ]

    async def pending_ship_ids(self, **_kwargs) -> set[str]:
        self.calls.append({"op": "pending"})
        return set(self.waiting)

    async def review_log(self, *, search: str = "", limit: int = 50, page: int = 1) -> list:
        self.calls.append({"op": "log", "search": search, "page": str(page)})
        if search:
            item = self.log.get(search)
            if item is None:
                return []
            return [_entry(search, "A Project", "someone", *item)]
        return self._rows(page, limit)

    async def aclose(self) -> None:
        pass


def _entry(ship_id, title, author, decision, reviewer, feedback="", *, when="5 minutes ago"):
    from clanker.stardance import ReviewLogEntry

    return ReviewLogEntry(
        ship_id=ship_id,
        title=title,
        author=author,
        decision=decision,
        reviewed_by=reviewer,
        when_text=when,
        feedback=feedback,
    )


@pytest.fixture
def log_cache(tmp_path) -> ReviewLogCache:
    """Named `log_cache` because pytest ships a `cache` fixture of its own."""
    return ReviewLogCache(tmp_path / "review_log_cache.json")


@pytest.fixture
def store_with(tmp_path):
    store = ResultStore(tmp_path)
    for cert_id, ship in (
        ("a", "15895"),  # reviewed + returned, not waiting -> leaves the queue
        ("b", "15900"),  # reviewed + approved, not waiting -> leaves the queue
        ("c", "16000"),  # waiting, no review yet -> stays
        ("d", "17000"),  # neither: a resubmission is a no-op, stays
    ):
        store._write(_record(cert_id, ship))
    return store


async def test_refresh_fills_in_every_ship(tmp_path, store_with) -> None:
    admin = FakeAdmin(
        waiting={"16000"},
        log={
            "15895": ("returned", "frog", "more than 30% AI"),
            "15900": ("approved", "kaboom", "nice"),
        },
    )
    summary = await StatusRefresher(admin, store_with).refresh()

    assert summary.checked == 4
    assert summary.decided == 2
    # Every record is written on a first pass: the two gain a decision, the other two are
    # confirmed as not waiting (None -> False).
    assert summary.changed == 4
    records = {r.cert_id: r for r in store_with.list()}
    assert records["a"].decision == "returned"
    assert records["a"].reviewed_by == "frog"
    assert records["a"].review_note == "more than 30% AI"
    assert records["a"].in_queue is False
    assert records["b"].decision == "approved"
    assert records["b"].in_queue is False
    assert records["c"].waiting is True
    assert records["c"].in_queue is True
    assert records["d"].decision is None
    assert records["d"].in_queue is True


async def test_a_returned_ship_that_was_resubmitted_stays_in_the_queue(tmp_path) -> None:
    store = ResultStore(tmp_path)
    store._write(_record("a", "15895"))
    admin = FakeAdmin(waiting={"15895"}, log={"15895": ("returned", "frog", "fix it")})
    summary = await StatusRefresher(admin, store).refresh()
    record = store.get("a")
    assert record.waiting is True
    assert record.in_queue is True
    # Its queue membership is settled by the waiting set, so the log is not consulted for it -
    # the second review will be read when the ship leaves the queue again.
    assert summary.lookups == 0
    assert record.decision is None


async def test_missing_ships_are_looked_up_one_by_one(tmp_path, store_with) -> None:
    """The recent log page missed a ship; a targeted search finds it."""
    admin = FakeAdmin(waiting=set(), log={})
    admin.log = {"15900": ("approved", "kaboom", "nice")}

    async def review_log(*, search: str = "", **_kwargs):
        admin.calls.append({"op": "log", "search": search})
        if search == "15900":
            return [_entry("15900", "A", "b", "approved", "kaboom", "nice")]
        return []  # the bulk page never covered our ships

    admin.review_log = review_log
    summary = await StatusRefresher(admin, store_with, backfill_limit=10).refresh()
    lookups = [c["search"] for c in admin.calls if c["op"] == "log" and c["search"]]
    assert len(lookups) == 4  # every tracked ship, since the bulk page found none
    assert summary.lookups == 4
    assert store_with.get("b").decision == "approved"


async def test_backfill_can_be_switched_off(tmp_path, store_with) -> None:
    admin = FakeAdmin(waiting=set(), log={})
    summary = await StatusRefresher(admin, store_with, backfill_limit=0).refresh()
    assert summary.lookups == 0
    assert all(r.decision is None for r in store_with.list())


async def test_maybe_refresh_respects_the_interval(tmp_path, store_with) -> None:
    admin = FakeAdmin(waiting={"16000"}, log={"15895": ("returned", "frog", "no")})
    refresher = StatusRefresher(admin, store_with, interval=300)

    first = await refresher.maybe_refresh()
    assert first is not None and first.decided == 1
    calls = len(admin.calls)

    # Inside the interval: no requests at all.
    assert await refresher.maybe_refresh() is None
    assert len(admin.calls) == calls


async def test_maybe_refresh_concurrent_readers_share_one_pass(tmp_path, store_with) -> None:
    import asyncio

    admin = FakeAdmin(waiting={"16000"}, log={})
    refresher = StatusRefresher(admin, store_with, interval=300)
    results = await asyncio.gather(*(refresher.maybe_refresh() for _ in range(5)))
    assert sum(1 for r in results if r is not None) == 1
    assert len([c for c in admin.calls if c["op"] == "pending"]) == 1


async def test_a_failure_never_propagates(tmp_path, store_with) -> None:
    """An expired Stardance session must not break the extension's request."""

    class Broken(FakeAdmin):
        async def pending_ship_ids(self, **_kwargs):
            raise StardanceAdminError("session cookie likely expired")

    refresher = StatusRefresher(Broken(set(), {}), store_with)
    summary = await refresher.maybe_refresh()
    assert summary is not None and "expired" in summary.error
    assert refresher.last_error is not None
    # ...and the records still read as "not decided" rather than being wiped.
    assert all(r.decision is None for r in store_with.list())


async def test_a_failure_does_not_retry_in_a_hot_loop(tmp_path, store_with) -> None:
    class Broken(FakeAdmin):
        calls = 0

        async def pending_ship_ids(self, **_kwargs):
            Broken.calls += 1
            raise StardanceAdminError("nope")

    refresher = StatusRefresher(Broken(set(), {}), store_with, interval=300)
    await refresher.maybe_refresh()
    await refresher.maybe_refresh()
    assert Broken.calls == 1


async def test_no_results_means_no_requests(tmp_path) -> None:
    admin = FakeAdmin(waiting={"1"}, log={"1": ("approved", "x", "")})
    summary = await StatusRefresher(admin, ResultStore(tmp_path)).refresh()
    assert summary.checked == 0
    assert admin.calls == []


async def test_records_without_a_ship_url_are_skipped(tmp_path) -> None:
    store = ResultStore(tmp_path)
    store._write(_record("no-url", ship=None))
    admin = FakeAdmin(waiting=set(), log={})
    summary = await StatusRefresher(admin, store).refresh()
    assert summary.checked == 1
    assert summary.requests == 0  # no ship id to look up, so nothing to ask Stardance
    assert store.get("no-url").decision is None


# ---------------------------------------------------------------- live client shape


async def test_client_requests_carry_the_session_and_ask_for_enough_rows() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/admin/certification/ship":
            return httpx.Response(200, text=QUEUE_HTML)
        return httpx.Response(200, text=REVIEW_LOG_HTML)

    admin = StardanceAdminClient("sess", transport=httpx.MockTransport(handler))
    try:
        waiting = await admin.pending_ship_ids()
        entries = await admin.review_log()
    finally:
        await admin.aclose()

    assert waiting == {"16000", "16001"}
    assert {e.ship_id for e in entries} == {"15895", "15900"}
    assert all("_stardance_session_4=sess" in r.headers.get("cookie", "") for r in seen)
    assert seen[0].url.params["status"] == "pending"
    assert int(seen[0].url.params["limit"]) >= 25


async def test_an_expired_session_is_reported_clearly() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://stardance.hackclub.com/"})

    admin = StardanceAdminClient("sess", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(StardanceAdminError, match="expired"):
            await admin.pending_ship_ids()
    finally:
        await admin.aclose()


# ---------------------------------------------------------------- request budget


def _settled(store, cert_id: str, ship: str) -> None:
    store._write(_record(cert_id, ship))
    store.set_review_state(cert_id, decision="returned", waiting=False, reviewed_by="frog")


def _page_requests(admin) -> list[dict[str, str]]:
    return [c for c in admin.calls if c["op"] == "log" and not c["search"]]


def _searches(admin) -> list[str]:
    return [c["search"] for c in admin.calls if c.get("search")]


async def test_a_settled_pass_costs_one_request(tmp_path) -> None:
    """Everything already decided and not waiting cannot have changed: read the queue, stop."""
    store = ResultStore(tmp_path / "results")
    for cert_id, ship in (("a", "15895"), ("b", "15900"), ("c", "16000")):
        _settled(store, cert_id, ship)
    admin = FakeAdmin(set(), {})
    summary = await StatusRefresher(
        admin, store, cache=ReviewLogCache(tmp_path / "c.json")
    ).refresh()

    assert summary.requests == 1
    assert [c["op"] for c in admin.calls] == ["pending"]
    # And nothing was lost by not asking about them.
    assert {r.decision for r in store.list()} == {"returned"}
    assert all(r.in_queue is False for r in store.list())


async def test_a_waiting_ship_is_not_looked_up(tmp_path, log_cache) -> None:
    """The sets are disjoint, so a ship that is waiting cannot have been reviewed."""
    store = ResultStore(tmp_path / "results")
    store._write(_record("a", "16000"))
    store.set_review_state("a", decision=None, waiting=True)
    admin = FakeAdmin({"16000"}, {})
    summary = await StatusRefresher(admin, store, cache=log_cache).refresh()
    assert summary.requests == 1 and summary.lookups == 0


async def test_a_waiting_ship_is_not_looked_up_every_pass(tmp_path, log_cache) -> None:
    """Otherwise every pending ship would cost a wasted lookup on every pass, forever."""
    store = ResultStore(tmp_path / "results")
    store._write(_record("a", "16000"))
    store.set_review_state("a", decision=None, waiting=True)
    admin = FakeAdmin({"16000"}, {})
    refresher = StatusRefresher(admin, store, cache=log_cache)
    await refresher.refresh()
    await refresher.refresh()
    assert admin.calls == [{"op": "pending"}, {"op": "pending"}]


async def test_only_unresolved_ships_are_looked_up(tmp_path, log_cache) -> None:
    store = ResultStore(tmp_path / "results")
    _settled(store, "settled", "15895")
    store._write(_record("unknown", "15900"))  # never reviewed, so it might be now
    admin = FakeAdmin(set(), {"15900": ("approved", "kaboom", "nice")})
    await StatusRefresher(admin, store, cache=log_cache).refresh()
    assert _searches(admin) == ["15900"]
    assert store.get("settled").decision == "returned"  # kept, not blanked
    assert store.get("unknown").decision == "approved"


async def test_a_resubmission_re_enters_the_queue_from_the_waiting_set(tmp_path, log_cache) -> None:
    store = ResultStore(tmp_path / "results")
    store._write(_record("a", "15895"))
    store.set_review_state("a", decision="returned", waiting=False)
    admin = FakeAdmin({"15895"}, {})
    summary = await StatusRefresher(admin, store, cache=log_cache).refresh()
    assert summary.requests == 1 and summary.lookups == 0
    assert store.get("a").waiting is True
    assert store.get("a").in_queue is True


async def test_a_ship_reviewed_again_after_a_resubmission_gets_a_fresh_reading(
    tmp_path, log_cache
) -> None:
    """We were watching it as waiting and it has now left the queue, so re-read its review."""
    store = ResultStore(tmp_path)
    store._write(_record("a", "15895"))
    store.set_review_state("a", decision="returned", waiting=True, reviewed_by="frog")
    admin = FakeAdmin(set(), {"15895": ("approved", "kaboom", "good now")})
    summary = await StatusRefresher(admin, store, cache=log_cache).refresh()
    assert summary.lookups == 1
    record = store.get("a")
    assert (record.decision, record.reviewed_by, record.waiting) == ("approved", "kaboom", False)
    assert record.in_queue is False


async def test_the_cache_answers_a_ship_for_free(tmp_path, store_with, log_cache) -> None:
    """Once a review is cached, no request is spent on that ship again."""
    admin = FakeAdmin(set(), {"15900": ("approved", "kaboom", "nice")})
    refresher = StatusRefresher(admin, store_with, cache=log_cache)
    await refresher.sync_cache(force=True)
    assert log_cache.get("15900") is not None

    admin.calls.clear()
    await refresher.refresh()
    assert "15900" not in _searches(admin)  # answered from the cache, at no cost
    assert store_with.get("b").decision == "approved"
    assert store_with.get("b").reviewed_by == "kaboom"
    assert store_with.get("b").review_note == "nice"


async def test_a_steady_cache_update_is_one_request(tmp_path, log_cache) -> None:
    """Nothing new happened, so the newest page adds nothing and we stop there."""
    log = {str(15000 + i): ("returned", "frog", "") for i in range(50)}
    admin = FakeAdmin(set(), log)
    refresher = StatusRefresher(
        admin, ResultStore(tmp_path / "results"), cache=log_cache, log_limit=50
    )
    # A cold fill also asks for page 2, to discover it has reached the end of the log.
    first = await refresher.sync_cache(force=True)
    assert (first.pages, first.added, log_cache.size) == (2, 50, 50)

    admin.calls.clear()
    second = await refresher.sync_cache(force=True)
    assert (second.pages, second.added) == (1, 0)  # steady state: one request, nothing new
    assert log_cache.size == 50


async def test_an_overlapping_page_is_followed_by_the_next_one(tmp_path, log_cache) -> None:
    """Fewer than 50 reviews since last time means the page overlapped: take the next one."""
    ids = [str(15000 + i) for i in range(70)]  # 70 rows: page 1 holds 50, page 2 the rest
    admin = FakeAdmin(set(), {i: ("returned", "frog", "") for i in ids}, page1=50)
    refresher = StatusRefresher(admin, ResultStore(tmp_path), cache=log_cache, log_limit=50)

    first = await refresher.sync_cache(force=True)
    assert first.added == 70 and log_cache.size == 70  # both pages, cold

    # Ten more reviews land, so the newest page is now 60 old rows + 10 new ones and the page
    # boundary has moved. Page 1 contributes the 10 new rows, so the update follows it to
    # page 2 to pick up the 10 that fell off the end.
    new = [str(16000 + i) for i in range(10)]
    admin.log.update({i: ("returned", "frog", "") for i in new})
    admin.page1 = 60
    admin.calls.clear()
    second = await refresher.sync_cache(force=True)
    assert second.pages == 2 and second.added == 10
    assert log_cache.size == 80
    assert len(_page_requests(admin)) == 2
    assert all(log_cache.get(ship) is not None for ship in ids + new)


async def test_a_cold_cache_catches_up_to_the_page_cap(tmp_path, log_cache) -> None:
    log = {str(15000 + i): ("returned", "frog", "") for i in range(500)}
    admin = FakeAdmin(set(), log, page1=50)
    refresher = StatusRefresher(
        admin, ResultStore(tmp_path / "results"), cache=log_cache, log_limit=50, cache_max_pages=3
    )
    summary = await refresher.sync_cache(force=True)
    assert summary.pages == 3 and log_cache.size == 150  # stopped at the cap, not the end


async def test_the_cache_survives_a_restart(tmp_path) -> None:
    path = tmp_path / "cache.json"
    first = ReviewLogCache(path)
    first.merge([_entry("15895", "A", "b", "returned", "frog", "fix it")])
    first.save()

    second = ReviewLogCache(path)
    second.load()
    assert second.get("15895").decision == "returned"
    assert second.get("15895").reviewed_by == "frog"
    assert second.get("15895").review_note == "fix it"
    assert second.newest_ship_id == "15895"
    assert second.merge([_entry("15895", "A", "b", "returned", "frog")]) == 0  # no duplicates


async def test_a_corrupt_cache_file_is_ignored(tmp_path) -> None:
    path = tmp_path / "cache.json"
    path.write_text("{not json")
    cache = ReviewLogCache(path)
    cache.load()
    assert cache.is_empty


async def test_the_cache_is_capped(tmp_path) -> None:
    cache = ReviewLogCache(tmp_path / "c.json", max_entries=10)
    cache.merge([_entry(str(15000 + i), "A", "b", "returned", "frog") for i in range(25)])
    assert cache.size == 10
    assert cache.newest_ship_id == "15024"
    assert cache.get("15024") is not None and cache.get("15000") is None


# ---------------------------------------------------------------- the boot sweep


async def test_the_startup_sweep_clears_ships_decided_while_the_bot_was_down(
    tmp_path, log_cache
) -> None:
    """The restart case: 90 judged ships, most decided while the bot was off."""
    store = ResultStore(tmp_path / "results")
    ships = [str(15000 + i) for i in range(90)]
    for ship in ships:
        store._write(_record(f"c{ship}", ship))
    decided = ships[:-3]  # all but the last few were reviewed while we were down
    admin = FakeAdmin(
        waiting=set(ships[-3:]), log={s: ("returned", "frog", "fix it") for s in decided}
    )
    refresher = StatusRefresher(
        admin, store, cache=log_cache, log_limit=50, cache_max_pages=4, startup_pages=20
    )

    cache_summary, summary = await refresher.startup_sweep()
    assert summary.checked == 90
    assert summary.decided == 87
    assert summary.waiting == 3
    assert cache_summary.pages >= 1
    # Whatever the cache did not cover was resolved by an individual lookup.
    assert summary.lookups == max(0, len(decided) - cache_summary.added)

    records = store.list()
    assert sum(1 for r in records if r.in_queue) == 3  # only the three still waiting
    assert all(r.reviewed_by == "frog" for r in records if not r.in_queue)


async def test_the_startup_sweep_moves_a_resubmitted_ship_back_into_the_queue(
    tmp_path, log_cache
) -> None:
    store = ResultStore(tmp_path / "results")
    store._write(_record("a", "15895"))
    store.set_review_state("a", decision="returned", waiting=False)
    # It was resubmitted and is waiting again while the bot was down.
    admin = FakeAdmin({"15895"}, {})
    await StatusRefresher(admin, store, cache=log_cache).startup_sweep()
    assert store.get("a").waiting is True
    assert store.get("a").in_queue is True


async def test_the_startup_sweep_is_not_a_hot_loop_on_failure(tmp_path, log_cache) -> None:
    """An expired session at boot must not spin."""
    store = ResultStore(tmp_path / "results")
    store._write(_record("a", "15895"))

    class Broken(FakeAdmin):
        async def pending_ship_ids(self, **_kwargs):
            raise StardanceAdminError("expired")

    refresher = StatusRefresher(Broken(set(), {}), store, cache=log_cache)
    cache_summary, summary = await refresher.startup_sweep()
    assert summary.error and "expired" in summary.error
    assert cache_summary.error is None  # the log read is a separate call and still works
    assert await refresher.maybe_refresh() is None  # the interval is honoured afterwards


async def test_a_background_reconcile_does_not_double_up_with_a_reader(tmp_path, log_cache) -> None:
    import asyncio

    store = ResultStore(tmp_path / "results")
    store._write(_record("a", "15895"))
    admin = FakeAdmin(set(), {"15895": ("returned", "frog", "")})
    refresher = StatusRefresher(admin, store, cache=log_cache)
    await refresher.sync_cache(force=True)
    admin.calls.clear()
    await asyncio.gather(refresher.reconcile(), refresher.reconcile())
    # Both passes ran, and neither needed a lookup because the cache already knew the review.
    assert len([c for c in admin.calls if c["op"] == "pending"]) == 2
    assert _searches(admin) == []


# ---------------------------------------------------------------- wiring


def test_no_refresher_without_a_stardance_session(tmp_path, caplog) -> None:
    from clanker.service import _build_refresher

    # Settings reads the repo's .env, so the session has to be cleared explicitly.
    settings = Settings(shipwrights_session="x", stardance_session="")
    assert _build_refresher(settings, ResultStore(tmp_path)) is None
    assert "STARDANCE_SESSION" in caplog.text


def test_no_refresher_when_switched_off(tmp_path) -> None:
    from clanker.service import _build_refresher

    settings = Settings(
        shipwrights_session="x", stardance_session="s", status_refresh_enabled=False
    )
    assert _build_refresher(settings, ResultStore(tmp_path)) is None


async def test_a_built_refresher_loads_its_cache(tmp_path) -> None:
    from clanker.service import _build_refresher

    cache_file = tmp_path / "cache.json"
    cache_file.write_text(
        '{"newest_ship_id": "15895", "updated_at": "x",'
        ' "entries": {"15895": {"decision": "returned", "reviewed_by": "frog"}}}'
    )
    settings = Settings(
        shipwrights_session="x", stardance_session="s", status_cache_file=cache_file
    )
    refresher = _build_refresher(settings, ResultStore(tmp_path))
    assert refresher is not None
    assert refresher.cache.get("15895").reviewed_by == "frog"
    await refresher.aclose()


def test_settings_default_to_refreshing() -> None:
    settings = Settings(shipwrights_session="x")
    assert settings.status_refresh_enabled is True
    assert settings.status_refresh_interval == 300.0
    assert settings.status_refresh_log_limit == 50
    assert settings.status_cache_interval == 1800.0
    assert settings.status_startup_sweep is True
