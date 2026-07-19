# 2026-07-19 — Sync review guidelines with hackclub/ship docs; drop submitter-identity commit check

## What

Researched the official Shipwrights guide site (github.com/hackclub/ship — the fumadocs
site behind the ship guidelines, cloned to scratchpad and read all `content/docs/*.mdx`)
plus the latest Slack-canvas guidelines, and updated the v2 reviewer prompts to match.

## Files touched

- `src/clanker/prompts/checks.md`
  - **check 4 (pre_event_commits)**: cutoff was a stale **December 25, 2024** (previous
    event); updated to **June 1, 2026** per the canvas ("any projects started before 1st
    of june should be marked as updated" / created before Stardance or submitted to
    another YSWS → updated project).
  - **check 6 (commit_authorship)**: removed the "submitter must match git commit
    author" logic per user request — git identities frequently differ from dashboard
    usernames, producing too many false positives. Check now only looks at history
    shape: fail = no commits; warn = single whole-project dump commit. The prompt now
    explicitly forbids comparing author names/emails to the submitter. Field name
    `commit_authorship` kept unchanged (baked into `review/models.py` ChecksResult and
    the PDF template).
  - **check 11 (demo_credentials)**: added API exception — the official API guide
    recommends providing test credentials/API keys, so those don't fail the check;
    rule targets user-account login flows.
  - **check 13 (demo_link_type)**: added Kaggle notebooks and tunnel links (ngrok,
    cloudflared, DuckDNS) to the universal rejects.
- `src/clanker/prompts/demo_guidelines.md` — full rewrite synced with ship docs.
  Notable changes vs the old version:
  - Minecraft mods: GitHub Release with the `.jar` is now **accepted** alongside
    Modrinth/CurseForge (old rule said avoid GitHub Releases); versions/loaders/
    dependencies must be listed. Other-game mods: Thunderstore/Nexus Mods; paid game →
    video demo.
  - iOS: App Store listing accepted in addition to TestFlight.
  - CLI: package managers preferred (incl. brew and `go install` from a tagged repo);
    GitHub Releases binary acceptable.
  - AI/ML: Kaggle added to rejects; browser-based inference (WebLLM/Transformers.js)
    valid; custom models must be bundled/auto-downloaded.
  - Hardware: demo video may live in the GitHub repo/release (not only YouTube);
    breadboard OK with wiring diagram; digital-only projects require a schematic;
    firmware required if physically built.
  - 3D/CAD: Printables/MakerWorld (Thingiverse dropped); must be physically printed
    with photos; editor + print files in repo; Tinkercad rejected.
  - Web apps: Cloudflare Pages listed as valid; HF added to hosting rejects.
  - APIs: Redoc/Scalar/RapiDoc accepted; must be deployed; test creds encouraged.
  - Extensions: `.vsix` added; demo link should point at the release.
  - Libraries: LuaRocks added; demo link = package page URL.
- `src/clanker/prompts/precheck.md` — Kaggle added to the early-screening flag list.
- `src/clanker/review/tools.py` — added `"kaggle.com": "kaggle"` to `_URL_FLAGS` and
  the docstring, so `review_check_url` actually flags it.

## Not touched

- `sw-reviewer/` (v1) — read-only reference per AGENTS.md.
- `review/models.py` — no field renames needed.

## Verification

`uv run pytest -q` → 36 passed.

## Open questions

- The June 1, 2026 cutoff comes from the canvas ("before 1st of june"); the ship docs
  don't state a cutoff. If the program defines a different exact date, adjust check 4.
- Several ship doc pages are still WIP (VR, iOS, auth, repo, shipwrights, GOI) — worth
  re-syncing once they're written.
