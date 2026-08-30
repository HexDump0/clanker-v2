# Audit Stardance and Dashboard behavior from HAR captures

**Date:** 2026-08-29 · **Agent:** Codex (GPT-5) · **Type:** research

## What was done
- Read the repository agent conventions, stable context, latest journal entries, and
  same-day audit notes before inspecting application code.
- Compared the Shipwrights client/models, watcher, review packet, and Stardance fetch tool
  with the two owner-provided HAR captures in `har/` without printing or persisting secrets.
- Replayed one read-only pending-list request using the captured Dashboard session. No
  claims, reviews, reports, notes, uploads, Slack writes, or other mutations were made.
- Ran the full test suite, Ruff, and the uv lock check.
- Added the HAR directory to `.gitignore` because HARs contain session cookies, CSRF data,
  personal data, and full response bodies.

## Why / decisions made
- The Dashboard is currently unusable through `ShipwrightsClient`: its custom
  `clanker/0.1` user agent received Cloudflare HTTP 403, while the same session and request
  with a browser user agent returned HTTP 200 and 48 pending certifications. This is a
  bot-filter compatibility issue, not an expired captured session.
- Current Dashboard detail responses expose resubmission history under `attempts[]`.
  Top-level `reviews[]` is empty for the captured pending attempt while four prior rejected
  attempts each contain a review. Clanker's model does not type attempts and its packet
  reads only top-level reviews, so it loses prior reviewer feedback.
- The Dashboard list supports multi-sort strings and its UI explicitly requests
  `sort=date:asc`; Clanker's client exposes no sort option. Detail responses also now
  include fields such as `aiEnabled`, `canReport`, `activeEvents`, and attempt history,
  while the current typed surface relies on `extra="allow"` and does not expose them to
  packet construction.
- The captured Dashboard JavaScript reveals a certification fraud-report endpoint. It is
  mutating and must remain outside agent tools unless a human-confirmed workflow is
  explicitly requested.
- The Stardance admin ship URL correctly redirects to the canonical public project URL,
  which the existing follow-redirect behavior handles. However, the tool flattens a large,
  duplicated responsive page and truncates visible text at 20,000 characters. A captured
  26-devlog project had 42,405 stripped characters, so older history is omitted. The HTML
  contains structured devlog IDs/timestamps, project stats, banner and media information
  that the tool currently does not return. Its documented `project_type` extraction did
  not match either captured project page.
- No application fixes were implemented because the owner requested an analysis and plan,
  not implementation. The only non-journal change is the explicitly requested ignore rule.

## Files touched
- `.gitignore` — modified — ignore the secret-bearing `har/` capture directory.
- `AI/journal/2026-08-29-09-har-stardance-dashboard-audit.md` — created — mandatory session
  record.

## Open questions / for the human
- Should the first implementation slice be limited to restoring Dashboard access and
  preserving attempt history, or also include the richer Stardance parser?
- Should returned certifications be watched automatically, or only fresh pending attempts?
- Should Dashboard-provided AI summaries be retained as non-authoritative comparison data,
  or excluded to keep Clanker's review independent?

## Next steps
- Replace the Dashboard user-agent behavior and add a Cloudflare-specific error category
  with a sanitized HAR-backed regression fixture.
- Model `attempts[]` and merge prior attempt reviews into the review packet with attempt
  identity, status, return reason, and timestamps.
- Add typed list sorting and make queue processing explicitly oldest-first.
- Replace whole-page Stardance text flattening with deterministic structured extraction of
  summary stats, banner state, and deduplicated devlogs, retaining bounded raw text only as
  fallback.
- Refresh `AI/context/API.md` alongside implementation so the stable reference matches the
  current response schema and new mutating endpoint.

## Verification
- Captured-session read-only replay: Clanker UA -> Cloudflare 403; browser UA -> JSON 200.
- `uv lock --check` -> passed.
- `uv run pytest -q` -> 58 passed, 1 pre-existing announcer failure (expected 2 Slack posts,
  implementation makes 3), plus two HTTPX per-request-cookie deprecation warnings.
- `uv run ruff check src tests` -> one pre-existing F541 in `slack/announcer.py`.
