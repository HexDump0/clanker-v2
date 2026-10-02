# The Clanker queue follows human decisions; new "All data" tab

**Date:** 2026-10-02 · **Agent:** opencode (space-bunny-free) · **Type:** feature

## What was done

- The Clanker queue now only holds ships a human still has to act on, and the Clanker page has a
  second tab with everything Clanker has ever judged. A ship's own verdict (reject / approve /
  needs human) never removes it from the queue; a **human's** decision does. The human asked for
  this and chose "any human decision, and resubmissions bring a ship back" over "approved only".
- `ResultRecord` gained `decision` (`approved` / `returned` / `None`), `reviewed_by`,
  `reviewed_at`, `review_note`, `waiting` and `checked_at`, plus a computed `in_queue`:
  not marked wrong, and either still waiting or never reviewed. `ship_id_of()` pulls the Stardance
  ship number out of the stored `stardance_url`. `set_review_state()` skips no-op writes;
  `save_outcome()` carries the human-decision fields across a re-review (without that, a re-review
  would drop a decided ship back into the queue).
- New `clanker.status.StatusRefresher` fills those fields. New review-log scraping in
  `clanker.stardance`: `parse_review_log`, `parse_relative_when`, `ReviewLogEntry`,
  `pending_ship_ids()`, `review_log()`.
- Trigger: three ways, all sharing one lock. **On demand** from `GET /api/results` behind
  `STATUS_REFRESH_INTERVAL`; a **background reconcile** every `STATUS_CACHE_INTERVAL` (30 min);
  and a **boot sweep** (`service.run_status_service`) that pulls further into the log and
  re-checks every tracked ship, because ships get decided while the bot is down and a restart
  must not leave them sitting in the queue. Wired in `service._build_refresher` and injected
  into `clanker.api.build_api(refresh=...)`. `maybe_refresh`, `reconcile`, `startup_sweep` and
  `list_results` all report failures rather than raising, so an expired session returns the last
  known states instead of breaking the extension's request.
- **Review-log cache** (`ReviewLogCache`, `data/review_log_cache.json`). The log is append-only
  with one immutable row per ship, so keeping it is what makes everything else cheap. A routine
  update fetches the newest 50 rows and stops when the page added nothing new; if a page only
  partly overlapped (fewer than 50 reviews since the last update) it takes the next page too,
  until the cache is contiguous again or `STATUS_CACHE_MAX_PAGES` is hit. A state pass is then
  **one request** (the waiting set) — settled ships and ships still waiting are answered without
  the log, and only a cache miss costs a lookup.
- Extension: `state.tab` / `state.scope` split the queue from All data, persisted in the
  sessionStorage it already writes. A **Human** column (waiting / not reviewed / approved /
  returned), per-tab stats bars, decision filters on All data, the human decision and the
  reviewer's own words on the banner, `Human` in the info card, and the Review card seeded from
  the stored decision instead of showing "–". A reject from the page now sets the decision
  locally so the row leaves the queue immediately. `page.css` gained the tab bar and a column.
- Docs: `.env.example`, `README.md`, `AI/context/API.md` (full review-log contract),
  `AI/context/v2-architecture-plan.md`.
- 299 tests pass, ruff clean. New `tests/test_status.py` (44 tests); three added to
  `tests/test_extension_api.py`.

## The source: Stardance's review log, not the Dashboard

I first planned to read cert statuses from the Shipwrights Dashboard API. The human pointed out
the watcher uses `stardance.hackclub.com`, and supplied the review-log URL. That turned out to be
strictly better, so the plan changed:

- `GET /admin/certification/ship/logs` is a log of **reviews**, not a queue: one row per reviewed
  ship with the outcome, who reviewed it, when, and their (truncated) feedback. It has no
  "rejected" outcome — a negative review is "returned".
- `limit` is honoured far past 25 (500 rows ≈ 60 KB, ~1 s) and `search=<bare ship id>` looks up a
  single ship in one request. The pending queue also takes `limit` (195 ships, one request).
- The two sets are **disjoint**: waiting ships have no log entry, reviewed ships are not waiting.
  Together they describe every ship, which is what `in_queue` is built on.
- Zero Dashboard traffic, and it reuses the session the watcher already has.

Verified live (read-only GETs, `.env`'s `STARDANCE_SESSION`; the cookie pasted into chat had
expired and 302s to `/`). Cross-checked against the 10 stored results: 3 decided — 15814
(vn_folks, returned by frog, *"more than 30% AI"*), 15812 and 15811 (both returned) — and 7
untouched. Clanker had said REJECT on 15812 and 15811 and both humans agreed.

## Decisions made

- **Not the watcher.** The watcher only ever looks at ships nobody has seen (it diffs against
  `seen_ids`), so it can never answer "was this one decided days ago". Separate object.
- **No standing timer.** The human dismissed the question; on-demand was the recommendation and
  nothing contradicted it, so that is what shipped.
- **Per-ship `search`, not page walking.** A `limit=500` walk skipped ids at the page boundary
  (page 1 ended 15301, page 2 began 15306) — the same flakiness the journals already record for
  the queue's `approved`/`returned` walks. One bulk page covers the common case, then targeted
  lookups fill the gaps (40/pass by default, 0 disables).
- **Only relative timestamps exist** ("3 minutes ago"), so `parse_relative_when` converts them to
  an approximate ISO and the UI recomputes the relative text.
- **Old records read optimistically.** `decision is None` means "not reviewed", so nothing
  vanishes from the queue before the first pass, and the extension falls back to
  `!manual_review` when talking to a server that predates the field.

## Request budget, measured live

Against the real pages with the 10 stored results:

| | Stardance requests |
|---|---|
| boot sweep | 21 (20 log pages + the waiting set), 1000 reviews cached, 0 lookups |
| routine pass | **2** (one 50-row log page + the waiting set) |
| pass, cache not due | **0** |
| settled pass, no cache fetch at all | **1** (the waiting set) |

Cache file: 1000 entries, 236 KB. The deployed instance has 87 results, so its boot sweep is
the same 21 requests plus whatever individual lookups the 1000-row cache cannot cover (5 at a
time, so a worst case of ~90 takes seconds, not minutes).

## Bugs found and fixed along the way

- Two pre-existing tests (`test_request_review_runs_once_then_cools_down`,
  `test_failed_review_reports_error`) charge the **real** `data/extension_usage.json` budget, so
  after ten suite runs in a day `POST /review` answers 429 and the job never starts. They were
  already failing before this work; they now use a `tmp_path` usage file.
- `_build_refresher` returning `None` was being appended to the close list, which would have
  crashed `run_all`'s `finally` whenever `STARDANCE_SESSION` was unset.
- The no-cache fallback wrote to `/dev/null.tmp` and raised `PermissionError`, which surfaced as
  a failed pass. `ReviewLogCache(None)` is now an explicitly in-memory cache.
- `startup_sweep` let an exception escape, unlike every other entry point; it now reports it.
- `summary.requests` counted log *entries* rather than requests on one path.
- A first pass over the design re-looked-up every still-waiting ship on **every** pass, forever.
  Caught by a test. The rule is now: only a ship that is not waiting, has no cached review, and
  could have moved is looked up.

## Not verified

- Never run against the live dashboard or a real Stardance session end to end; the refresher's
  tests use a fake admin client and `httpx.MockTransport`.
- The extension changes were driven in Chromium against mocked API responses (Playwright
  screenshots in the session scratchpad), not in a loaded extension on a real dashboard.
- `WATCHER_SOURCE=dashboard` is untested here: the refresher does not care (it only needs
  `STARDANCE_SESSION`), but that combination has never been run.

## Files touched

- `src/clanker/status.py`, `tests/test_status.py` — created.
- `src/clanker/{results.py,stardance.py,api.py,service.py,config.py}` — modified.
- `extension/{judgements.js,ui.js,page.css}` — modified.
- `.env.example`, `README.md`, `AI/context/{API.md,v2-architecture-plan.md}` — modified.
- `tests/test_extension_api.py` — modified (three new tests + the usage-file isolation fix).

## Open questions / for the human

- The review log truncates feedback at ~120 characters. Fine for "why did a human bounce this",
  useless for full text. Is the untruncated comment worth chasing (it would need the Dashboard's
  `reviews[]`, i.e. Dashboard traffic after all)?
- Ships Clanker reviewed long ago fall outside the cached window and cost one lookup each
  (40/pass, 5 at a time). The boot sweep uses the full `max_lookups` (200) instead, so it clears
  the current backlog in one go.
- "Agreement" still counts only explicit right/wrong labels. Now that we know each ship's human
  outcome, it could be computed automatically (Clanker said reject and the human returned it) —
  that is the precision number the evals use. Deliberately not done; it is a product decision.

## Next steps

- Redeploy: the boot sweep will reconcile the ~87 existing results, so decided ships move out of
  the Clanker queue on first start (`STATUS_STARTUP_SWEEP=true` by default).
- Watch the first passes in Logfire ("Startup sweep: … | …", "Review-log cache: …",
  "Ship review states: …") and confirm decided ships drop out while humans are working through
  the queue.
- Rebuild the extension (`API_URL=… ./build.sh`) when the next release goes out.
