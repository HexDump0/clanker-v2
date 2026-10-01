# GitLab / other forges, a video scene for every reason, errors to Logfire

**Date:** 2026-10-01 · **Agent:** Claude Code (Opus 5.5) · **Type:** fix

## What happened
- The first live production review (cert `5c63c876…`, a GitLab repo) was wrongly rejected for
  "no README" plus "thin README", and its video "failed". Root cause: the Dashboard README cache only covers GitHub
  (`status: not_github`), so the packet had no README. Separately, the video planner only built scenes for GitHub repos, so
  no reason mapped to a scene and `generate_reject_video` raised.
- Logfire: the bot's `.env` sends to the **`sw-clanker-bench`** project (`LOGFIRE_SERVICE_NAME=sw-clanker-bench`,
  with a token from that project), not `clanker-v2`. Only HTTP and model spans were there. Stdlib `logger.exception` output
  (such as the video failure) was never forwarded.

## What was done
- New `src/clanker/forges.py`: `parse_repo` (GitHub, GitLab incl. nested groups and `gitlab.*` hosts,
  Codeberg/Gitea/Forgejo, Bitbucket, sourcehut), `Repo.blob_url/raw_url/releases_url/web_url`,
  `is_raw_file_url`, `raw_readme_url`, and `fetch_readme`. All forges accept `HEAD` as a ref (checked live).
- Packet: for a non-GitHub repo with no cached README, it fetches the README from the forge
  (`readme_source`). If the network fails, it sets `readme_unverified` and the prompt shows "not verified".
- First layer:
  - facts: `readme_url_is_raw` (any forge), `repo_host`, `readme_unverified`, and a forge-aware `repo_url_is_repo_root`
    (`readme_url_is_raw_github` is kept for the old eval).
  - rules: `no_readme` never fires on an unverified README. `ai_readme`/`readme_thin` are skipped when
    there's no README (previously "no README" plus "needs more detail" both fired). `readme_not_raw` accepts any forge's raw link.
    `missing_build` also covers GitLab/Gitea release pages.
  - evidence: code excerpts and release assets for GitLab (REST tree, GraphQL blob sizes, raw files,
    release links) and Gitea (tree with sizes, raw, releases). The forge file list goes to Jev as `repo_structure`
    when the packet has no GitHub tree.
- Reject message: the raw-link fix now uses the forge's raw URL, and the hint is generic for non-GitHub repos.
- Video: scene URLs come from `Repo`. Per the human ("add a video scene for all reject reason"), every reason
  in `ORDER` now gets a scene: the live page when possible, otherwise a text card (`FALLBACK_CARDS`, which
  also covers `feedback_ignored`/`not_eligible`). The runner still skips the video if `plan_scenes` is empty
  (only for unknown reasons).
- `configure_observability` attaches a `LogfireLoggingHandler` at WARNING, so errors and tracebacks reach Logfire.
- Tests: `tests/test_forges.py` (URL helpers, README fallback/unverified, rules, message, video URLs, every
  reason → scene, runner card video). `tests/conftest.py` FakeDashboard has a configurable `readme`.
  `uv run pytest -q`: 191 passed. Ruff is clean.
- Live: re-review of `5c63c876…` → README from GitLab (1651 chars), 40 code files, iOS App, **PASS to a
  human** with near misses ai_code 0.61 / ai_readme 0.68. A forced GitLab reject video (3 scenes, 25 s)
  captured GitLab pages fine (no bot wall).

## Not done / notes
- `demo_not_testable` has no threshold and is not in `ORDER`, so it can never reject, and it has no message or scene.
- Bitbucket/sourcehut: README and links only. No code excerpts or release assets, so the AI-code and missing-build checks
  stay silent (pass to a human).
- The running bot (started before these changes) must be restarted to pick them up.

## Open questions / for the human
- Move Logfire to the `clanker-v2` project (needs a write token from that project, plus `LOGFIRE_SERVICE_NAME`)?
- Nothing is committed yet (branch `jev-first-layer-eval`).

## Files touched
- `src/clanker/forges.py` — created.
- `src/clanker/review/{packet.py,runner.py,reject_message.py}`, `src/clanker/review/first_layer/{facts.py,rules.py,evidence.py,reviewer.py}`,
  `src/clanker/review/video/template_director.py`, `src/clanker/config.py` — modified.
- `tests/test_forges.py` — created. `tests/conftest.py` — modified.
- `README.md`, `AI/context/v2-architecture-plan.md` — modified.
