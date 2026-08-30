# Redirect-probe reconciliation + announce-at-detection for the Stardance watcher

**Date:** 2026-08-30 · **Agent:** opencode (GLM) · **Type:** feature

## What was done
- Replaced the PENDING-page-walk reconciliation with the owner-discovered redirect
  probe: `GET /admin/certification/ship/<id>` 302s to
  `https://ds.shipwrights.dev/stardance/certifications/<uuid>` once the Dashboard has
  imported the ship; ships the Dashboard does not know render HTTP 200 (review page).
  The cert id falls out of the redirect's last path segment.
- New resolution flow in `StardancePendingSource.resolve` (per newly detected ship):
  1. announce immediately from Stardance data (before any reconciliation);
  2. probe the admin ship page; on a miss wait 10s and probe once more
     (`DASH_PROBE_RETRY_DELAY`, one retry only, per owner spec);
  3. redirect -> `dashboard.get_certification(<uuid>)` -> emit `PendingEmission`;
  4. second miss -> treat as dash-down: log, drop the ship (it is already marked
     seen), flip the announcement embed to `DASH DOWN`, and post a dash-crash note in
     the announcement thread; no automated review runs.
- Stardance announcements are now first-class: `Announcer.announce_ship_from_stardance`
  (headline + cc ping, embed with title/type/AUTOMATING, author + queue-wait fields,
  links: Stardance admin ship URL as `#<id>` plus Demo/Repo taken from the queue row)
  and `Announcer.announce_dash_down` (embed flip + thread note). The queue-row parser
  now also extracts `project_type` (`ship-queue__type-tag`), `demo_url`, and
  `repo_url` (`ship-queue__quick-link` anchors labelled Demo/Repo).
- Watcher contract change: `poll_once()`/`PendingSource.resolve()` now return
  `PendingEmission` objects (`cert` + optional `parent_ts`). The Stardance source
  pre-announces at detection and threads the review under that message; the Dashboard
  source keeps announcing at emit time (`parent_ts=None`). Fresh keys are de-duplicated
  per poll as defence against queue shifts mid-walk.
- Removed the old reconcile machinery entirely: the per-poll Dashboard PENDING scan,
  the `_awaiting` retry map, and `RESOLVE_MAX_AGE` (6h) are gone.

## Why / decisions made
- The goal was reducing Shipwrights Dashboard strain; the old reconcile still hit the
  Dashboard once per poll while any ship awaited import (~2,880 req/day, same as the
  old watcher). The probe is per-new-ship, hits Stardance not the Dashboard, so
  Dashboard load from watching is now ~1 `get_certification` per imported ship —
  effectively zero. The remaining Dashboard traffic is the review pipeline itself
  (~6 reqs per ship).
- Per the owner's spec, a ship that never redirects (even after the 10s retry) is
  ignored, not retried forever; with the import currently lagging, this means such
  ships get announced but not reviewed until/unless they are detected another way.
  Owner accepted this trade-off explicitly.
- `PendingEmission.parent_ts` threads the review under the detection-time
  announcement, so `review_and_report` no longer re-announces for Stardance ships.

## Files touched
- `src/clanker/stardance.py` — modified — AdminShip gains project_type/demo_url/repo_url;
  parser updated; `ship_redirect_target` probe + `parse_dash_cert_id`.
- `src/clanker/watcher.py` — modified — `PendingEmission`, probe-based resolution,
  detection-time announcements, fresh-key dedupe, removed awaiting/RESOLVE_MAX_AGE.
- `src/clanker/slack/announcer.py` — modified — `announce_ship_from_stardance`,
  `announce_dash_down`, `DASH DOWN` status style.
- `src/clanker/service.py` — modified — `review_and_report`/handler take emissions and
  skip re-announcing when `parent_ts` exists; announcer passed to the source factory.
- `src/clanker/cli.py` — modified — `watch` announce callback handles emissions.
- `tests/test_stardance_watcher.py`, `tests/test_watcher.py` — modified — new flow
  coverage: redirect resolve, dash-down crash path, announce-at-detection, parser
  fields, empty page walks. `uv run pytest -q` -> 84 passed; ruff clean.
- `AI/context/API.md` — modified — ship-page redirect probe documented.

## Open questions / for the human
- Ships dropped as dash-down are never revisited automatically (owner-accepted).
  If the import outage outlasts detection, those ships will simply never be reviewed.

## Next steps
- Optional follow-ups discussed: adaptive poll interval (still 30s fixed), and a
  human-observed full `run_review` once the import recovers.

## Verification
- Live, read-only: newest ship 11088 (not imported) probed twice and dropped with the
  dash-down path; ship 10254 redirected, cert id parsed, and the full CertSummary
  ('IrBlaster-API') fetched via `get_certification`. No Slack writes, no mutations.
