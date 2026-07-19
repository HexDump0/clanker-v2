from __future__ import annotations

import json

from clanker.watcher import Watcher, WatcherState
from tests.conftest import make_cert


async def test_first_run_records_backlog_without_emitting(client, dashboard, tmp_path):
    dashboard.set_pending([make_cert("c1"), make_cert("c2")])
    state_file = tmp_path / "state.json"
    watcher = Watcher(client, state_file=state_file)

    assert await watcher.poll_once() == []
    saved = json.loads(state_file.read_text())
    assert set(saved["seen_ids"]) == {"c1", "c2"}


async def test_first_run_emits_backlog_when_configured(client, dashboard, tmp_path):
    dashboard.set_pending([make_cert("c1")])
    watcher = Watcher(client, state_file=tmp_path / "state.json", emit_backlog=True)
    assert [c.id for c in await watcher.poll_once()] == ["c1"]


async def test_new_certs_detected_across_polls(client, dashboard, tmp_path):
    dashboard.set_pending([make_cert("c1")])
    watcher = Watcher(client, state_file=tmp_path / "state.json")
    await watcher.poll_once()

    dashboard.set_pending([make_cert("c1"), make_cert("c2")])
    assert [c.id for c in await watcher.poll_once()] == ["c2"]

    # nothing new -> nothing emitted
    assert await watcher.poll_once() == []


async def test_state_survives_restart(client, dashboard, tmp_path):
    """Certs that arrived while the watcher was down are still emitted."""
    state_file = tmp_path / "state.json"
    dashboard.set_pending([make_cert("c1")])
    await Watcher(client, state_file=state_file).poll_once()

    # watcher "restarts"; c2 arrived in the meantime
    dashboard.set_pending([make_cert("c1"), make_cert("c2")])
    fresh = await Watcher(client, state_file=state_file).poll_once()
    assert [c.id for c in fresh] == ["c2"]


async def test_unchanged_queue_costs_one_request(client, dashboard, tmp_path):
    dashboard.set_pending([make_cert(f"c{i}") for i in range(120)], per_page=50)  # 3 pages
    watcher = Watcher(client, state_file=tmp_path / "state.json")
    await watcher.poll_once()  # first run: full walk

    dashboard.requests.clear()
    assert await watcher.poll_once() == []
    assert len(dashboard.requests) == 1  # fingerprint unchanged -> page 1 only

    # a new cert changes the total -> full walk again, new cert emitted
    dashboard.set_pending([make_cert(f"c{i}") for i in range(121)], per_page=50)
    dashboard.requests.clear()
    fresh = await watcher.poll_once()
    assert [c.id for c in fresh] == ["c120"]
    assert len(dashboard.requests) == 3


def test_corrupt_state_starts_fresh(tmp_path):
    state_file = tmp_path / "state.json"
    state_file.write_text("{not json")
    assert WatcherState.load(state_file) is None
