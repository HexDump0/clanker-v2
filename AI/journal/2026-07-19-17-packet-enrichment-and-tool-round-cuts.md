# Packet enrichment + tool-round reduction (from run cost analysis)

**Date:** 2026-07-19 · **Agent:** Claude (Fable 5) · **Type:** feature

## What was done

Implemented improvements 1–3 from the trace analysis in
`2026-07-19-16-review-run-cost-analysis.md`:

1. **No routine re-fetching of packet data.** `system.md` now says to trust the
   packet by default and re-fetch README/commits/tree/languages/Stardance page
   only with a concrete reason to doubt the copy (stale, truncated,
   inconsistent, suspiciously empty) — per the human, the agent keeps the
   freedom to re-verify data that looks wrong. Tool docstrings for
   `review_get_github_readme` / `_commits` / `_languages` / `_repo_tree` /
   `review_fetch_stardance_project` changed from "cross-check" language to
   match.
2. **Packet enrichment.** `build_packet(client, cert_id, tools=None)` now
   pre-fetches (concurrently, via the existing ReviewTools methods) the repo
   file tree, language breakdown, and the Stardance admin ship page, rendered
   into the prompt as "Repo structure (pre-fetched)" and "Stardance ship page
   (pre-fetched)" sections. Failed enrichment is skipped silently *except* the
   Stardance fetch, whose error payload is surfaced (redirected_away is a
   review signal). `ReviewRunner` gained a `tools` param; `service.build_app`
   passes the shared ReviewTools instance.
3. **Merged reachability into `review_fetch_page_text`.** It now returns
   `final_url`, `status_code`, `reachable`, and platform `flags` (same
   `_URL_FLAGS` set as `review_check_url`), including on the HTTP-error and
   challenge branches, so a check_url + fetch_page_text pair on the same URL
   collapses to one call. Prompt updated to say so.

Expected effect on the trace profile: ~6 model rounds → ~3, roughly halving
input tokens and ~25 s of latency per review.

## Files touched

- `src/clanker/review/packet.py` — modified — enrichment fields, concurrent
  build, new prompt sections (Stardance text capped at 12k chars).
- `src/clanker/review/tools.py` — modified — fetch_page_text reachability,
  docstring rewordings.
- `src/clanker/review/runner.py` — modified — optional `tools` param threaded
  to build_packet.
- `src/clanker/service.py` — modified — pass tools into ReviewRunner.
- `src/clanker/prompts/system.md` — modified — packet contents list, "NEVER
  re-fetch" rule, tool guidance updates.
- `tests/test_review.py` — modified — 3 new tests: enriched packet prompt,
  no-tools packet unchanged, fetch_page_text reachability payload.

## Verification

`uv run pytest tests/` — 31 passed. `ruff check` clean (pre-existing format
drift in untouched files left alone).

## Next steps

- Not done (deliberately, was improvement 4/5): `max_chars` param on
  `review_get_github_file_content`; gating `review_get_github_releases` by
  project type.
- Verify on a live run that rounds actually drop and the prompt-cache hit
  pattern holds (packet is per-cert, so only instructions+tools prefix caches).
