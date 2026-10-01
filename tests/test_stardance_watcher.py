"""Tests for the Stardance admin queue source and its watcher integration."""

from __future__ import annotations

import json
import re

import httpx

from clanker.shipwrights import ShipwrightsClient
from clanker.stardance import (
    STARDANCE_COOKIE_NAME,
    StardanceAdminClient,
    parse_dash_cert_id,
    parse_queue,
)
from clanker.watcher import (
    PendingEmission,
    ShipwrightsPendingSource,
    StardancePendingSource,
    Watcher,
)
from tests.conftest import make_cert

DASH_CERT_ID = "3a8f1d67-36a4-4c45-978c-4f87572c91e7"
DASH_URL = f"https://ds.shipwrights.dev/stardance/certifications/{DASH_CERT_ID}"

QUEUE_HTML = """
<html><body>
<div class="ship-queue__metrics">
  <div class="ship-queue__metric">
    <span class="ship-queue__label">In queue</span>
    <span class="ship-queue__metric-value">105</span>
  </div>
  <div class="ship-queue__metric">
    <span class="ship-queue__label">Oldest waiting</span>
    <a class="ship-queue__metric-link" href="/admin/certification/ship/1634">2 months</a>
  </div>
</div>
<table><tbody>
  <tr class="ship-queue__row ship-queue__row--link"
      onclick="window.location='/admin/certification/ship/11077'">
    <td class="ship-queue__cell-project">
      <span class="ship-queue__project-title">nasa</span>
      <span class="ship-queue__project-id">#11077</span>
      <a target="_blank" rel="noopener" class="ship-queue__quick-link"
         onclick="event.stopPropagation()"
         href="https://nasa-apod.example.io/">Demo</a>
      <a target="_blank" rel="noopener" class="ship-queue__quick-link"
         onclick="event.stopPropagation()"
         href="https://github.com/piyushoutthere/nasa-apod">Repo</a>
    </td>
    <td class="ship-queue__cell-author">
      piyushoutthere
    </td>
    <td class="ship-queue__cell-type">
      <span class="ship-queue__type-tag">Web App</span>
    </td>
    <td class="ship-queue__cell-wait"><span class="ship-queue__wait-badge">0d</span></td>
    <td class="ship-queue__cell-hours"><span class="ship-queue__hours">0.3h</span></td>
    <td class="ship-queue__cell-status">
      <span class="status-pill status-pill--pending">Pending</span>
      <span class="status-pill status-pill--pending">Pending</span>
    </td>
  </tr>
  <tr class="ship-queue__row">
    <td class="ship-queue__cell-project">
      <span class="ship-queue__project-title">old ship</span>
      <span class="ship-queue__project-id">#11076</span>
    </td>
    <td class="ship-queue__cell-author">
      someoneelse
    </td>
    <td class="ship-queue__cell-type">
      <span class="ship-queue__muted">&mdash;</span>
    </td>
    <td class="ship-queue__cell-wait"><span class="ship-queue__wait-badge">1d</span></td>
    <td class="ship-queue__cell-hours"><span class="ship-queue__hours">12h</span></td>
    <td class="ship-queue__cell-status">
      <span class="status-pill status-pill--returned">Returned</span>
    </td>
  </tr>
</tbody></table>
</body></html>
"""

EMPTY_PAGE_HTML = """
<html><body>
<div class="ship-queue__metrics">
  <span class="ship-queue__label">In queue</span>
  <span class="ship-queue__metric-value">105</span>
</div>
<table><tbody></tbody></table>
</body></html>
"""


def stardance_transport(redirects: dict[str, str | None] | None = None):
    """Mock transport: queue list + per-ship pages (302 to dash or plain 200)."""
    redirects = redirects or {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/admin/certification/ship":
            return httpx.Response(200, text=QUEUE_HTML)
        m = re.fullmatch(r"/admin/certification/ship/(\d+)", path)
        if m:
            target = redirects.get(m.group(1))
            if target == "login":
                return httpx.Response(302, headers={"location": "/login"})
            if target:
                return httpx.Response(302, headers={"location": target})
            return httpx.Response(200, text="<html>old review page</html>")
        return httpx.Response(404, text="")

    return httpx.MockTransport(handler)


def stardance_client(redirects: dict[str, str | None] | None = None) -> StardanceAdminClient:
    return StardanceAdminClient("test-session", transport=stardance_transport(redirects))


class FakeAnnouncer:
    """Records Stardance announcement calls instead of posting to Slack."""

    def __init__(self) -> None:
        self.announced: list[str] = []
        self.dash_down: list[str] = []
        self.failures: list[str] = []

    async def announce_ship_from_stardance(self, ship, *, ship_url: str) -> str:
        self.announced.append(ship.ship_id)
        return "111.222"

    async def announce_dash_down(self, ship, *, ship_url: str, parent_ts: str | None) -> None:
        self.dash_down.append(ship.ship_id)

    async def post_failure(self, parent_ts: str) -> None:
        self.failures.append(parent_ts)


async def test_parse_queue_extracts_metrics_and_rows() -> None:
    page = parse_queue(QUEUE_HTML)
    assert page.total == 105
    assert [s.ship_id for s in page.ships] == ["11077", "11076"]
    first, second = page.ships
    assert first.title == "nasa"
    assert first.author == "piyushoutthere"
    assert first.status == "pending"
    assert first.wait == "0d"
    assert first.hours == "0.3h"
    assert first.project_type == "Web App"
    assert first.demo_url == "https://nasa-apod.example.io/"
    assert first.repo_url == "https://github.com/piyushoutthere/nasa-apod"
    # duplicated responsive pills collapse to one status; muted dash -> no type
    assert second.status == "returned"
    assert second.project_type == ""
    # the "oldest waiting" metric link (ship 1634) is not a queue row
    assert "1634" not in {s.ship_id for s in page.ships}


async def test_parse_queue_missing_metric_raises() -> None:
    import pytest

    from clanker.stardance import StardanceAdminError

    with pytest.raises(StardanceAdminError):
        parse_queue("<html><body>login page</body></html>")


async def test_parse_dash_cert_id_takes_last_segment() -> None:
    assert parse_dash_cert_id(DASH_URL) == DASH_CERT_ID
    assert parse_dash_cert_id("https://ds.shipwrights.dev/stardance/certifications/abc/") == "abc"


async def test_admin_client_sends_session_cookie() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text=QUEUE_HTML)

    client = StardanceAdminClient("secret", transport=httpx.MockTransport(handler))
    page = await client.queue_page()
    await client.aclose()
    assert page.total == 105
    assert seen[0].url.path == "/admin/certification/ship"
    assert seen[0].url.params["status"] == "pending"
    assert seen[0].url.params["sort"] == "newest"
    cookie_header = next(h for h in seen[0].headers.get_list("cookie"))
    assert cookie_header.startswith(f"{STARDANCE_COOKIE_NAME}=")
    assert "secret" in cookie_header


async def test_ship_redirect_target_reports_dashboard_import() -> None:
    import pytest

    from clanker.stardance import StardanceAdminError

    client = StardanceAdminClient(
        "test-session",
        transport=stardance_transport({"10254": DASH_URL, "99999": "login"}),
    )
    assert await client.ship_redirect_target("10254") == DASH_URL
    assert await client.ship_redirect_target("11076") is None  # no redirect -> not imported
    with pytest.raises(StardanceAdminError, match="session cookie"):
        await client.ship_redirect_target("99999")
    await client.aclose()


async def test_stardance_source_resolves_via_redirect(
    client: ShipwrightsClient, dashboard, tmp_path
) -> None:
    redirects = {"11077": DASH_URL}  # 11076 does not redirect (not imported)
    dashboard.details[DASH_CERT_ID] = make_cert(DASH_CERT_ID, externalId="11077")
    source = StardancePendingSource(stardance_client(redirects), client, probe_retry_delay=0.01)
    page = await source.pending_page(1)
    assert page.total == 105
    assert page.pages == 5  # ceil(105 / 25)
    assert [item.key for item in page.items] == ["11077", "11076"]

    emissions = await source.resolve(["11077", "11076"])
    # 11077 redirected to the dashboard -> resolved with the right cert;
    # 11076 never redirected -> dash down, dropped
    assert [e.cert.id for e in emissions] == [DASH_CERT_ID]
    assert emissions[0].parent_ts is None  # no announcer wired
    assert emissions[0].cert.external_id == "11077"


async def test_stardance_source_announces_at_detection(
    client: ShipwrightsClient, dashboard, tmp_path
) -> None:
    dashboard.details[DASH_CERT_ID] = make_cert(DASH_CERT_ID, externalId="11077")
    announcer = FakeAnnouncer()
    source = StardancePendingSource(
        stardance_client({"11077": DASH_URL}),
        client,
        announcer=announcer,
        probe_retry_delay=0.01,
    )
    await source.pending_page(1)
    emissions = await source.resolve(["11077"])
    assert announcer.announced == ["11077"]
    assert [e.parent_ts for e in emissions] == ["111.222"]
    assert announcer.dash_down == []


async def test_stardance_source_dash_down_announces_crash(
    client: ShipwrightsClient, dashboard, tmp_path
) -> None:
    announcer = FakeAnnouncer()
    source = StardancePendingSource(
        stardance_client({}), client, announcer=announcer, probe_retry_delay=0.01
    )
    await source.pending_page(1)
    emissions = await source.resolve(["11076"])
    assert emissions == []
    assert announcer.announced == ["11076"]  # announced at detection anyway
    assert announcer.dash_down == ["11076"]


async def test_stardance_source_no_announcer_still_resolves(
    client: ShipwrightsClient, dashboard, tmp_path
) -> None:
    dashboard.details[DASH_CERT_ID] = make_cert(DASH_CERT_ID, externalId="11077")
    source = StardancePendingSource(
        stardance_client({"11077": DASH_URL}), client, probe_retry_delay=0.01
    )
    await source.pending_page(1)
    emissions = await source.resolve(["11077"])
    assert [e.cert.id for e in emissions] == [DASH_CERT_ID]


async def test_watcher_with_stardance_source_emits_only_imported(
    client: ShipwrightsClient, dashboard, tmp_path
) -> None:
    dashboard.details[DASH_CERT_ID] = make_cert(DASH_CERT_ID, externalId="11077")
    html_holder = {"html": QUEUE_HTML}
    redirects = {"11077": DASH_URL}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/admin/certification/ship":
            if int(request.url.params.get("page", "1")) > 1:
                return httpx.Response(200, text=EMPTY_PAGE_HTML)
            return httpx.Response(200, text=html_holder["html"])
        m = re.fullmatch(r"/admin/certification/ship/(\d+)", path)
        if m:
            target = redirects.get(m.group(1))
            if target:
                return httpx.Response(302, headers={"location": target})
            return httpx.Response(200, text="<html>old review page</html>")
        return httpx.Response(404, text="")

    admin = StardanceAdminClient("test-session", transport=httpx.MockTransport(handler))
    watcher = Watcher(
        StardancePendingSource(admin, client, probe_retry_delay=0.01),
        state_file=tmp_path / "state.json",
    )

    # first run records the backlog (including ship 11076 with no dashboard cert)
    assert await watcher.poll_once() == []

    # ship 11078 appears on stardance and the dashboard imports it -> emitted
    new_cert_id = "bbbbbbbb-36a4-4c45-978c-4f87572c91e7"
    html_holder["html"] = QUEUE_HTML.replace("#11076", "#11078")
    redirects["11078"] = DASH_URL.replace(DASH_CERT_ID[:8], "bbbbbbbb")
    dashboard.details[new_cert_id] = make_cert(new_cert_id, externalId="11078")
    fresh = await watcher.poll_once()
    assert [e.cert.id for e in fresh] == [new_cert_id]


async def test_watcher_state_source_switch_records_without_emitting(
    client: ShipwrightsClient, dashboard, tmp_path
) -> None:
    """Switching sources must not flood-emit the whole queue as 'new'."""
    dashboard.set_pending([make_cert("c1"), make_cert("c2")])
    state_file = tmp_path / "state.json"
    await Watcher(ShipwrightsPendingSource(client), state_file=state_file).poll_once()

    # switch to stardance: keys are a different namespace, so the watcher
    # records the current queue first instead of emitting everything.
    source = StardancePendingSource(stardance_client({}), client, probe_retry_delay=0.01)
    watcher = Watcher(source, state_file=state_file)
    assert await watcher.poll_once() == []
    saved = json.loads(state_file.read_text())
    assert saved["source"] == "stardance"
    assert set(saved["seen_ids"]) == {"11077", "11076"}


async def test_pending_emission_defaults() -> None:
    from clanker.shipwrights import CertSummary

    cert = CertSummary.model_validate(make_cert("c1"))
    emission = PendingEmission(cert=cert)
    assert emission.parent_ts is None
