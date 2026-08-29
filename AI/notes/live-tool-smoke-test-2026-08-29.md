# Live Clanker tool smoke test — 2026-08-29

Read-only live smoke test using the repo's current `.env`. No secret values were
printed or persisted. No Shipwrights mutations, Slack messages/uploads, reviews, claims,
or verdict submissions were attempted.

## Registered review tools

| Tool | Result | Live evidence |
|---|---|---|
| `get_github_repo_info` | PASS | Public repo metadata returned. |
| `get_github_readme` | PASS | README content returned. |
| `get_github_commits` | PASS | Requested commits returned. |
| `get_github_languages` | PASS | Language breakdown returned. |
| `get_github_repo_tree` | PASS | Recursive tree returned with truncation reported correctly. |
| `get_github_file_content` | PASS | Requested README file returned. |
| `get_github_releases` | PASS | Ten releases returned for the fixture repository. |
| `search_github_code` | PASS | Twenty matches returned; this also verifies authenticated GitHub code search. |
| `check_url` | PASS | `example.com` reported reachable with HTTP 200. |
| `fetch_page_text` | PASS | HTTP 200 and extracted text returned. |
| `render_page` | PASS | Chromium rendered the page and the configured vision model described it. |
| `fetch_stardance_project` | PASS | After changing the cookie name from stale `_stardance_session_v3` to current `_stardance_session_4`, three authenticated live ship fetches returned metadata and page text. |
| `check_package` | PASS | PyPI package metadata returned. |
| `web_search` | PASS | Hack Club Exa proxy returned two results. |

Result: **14/14 registered review tools pass**.

## Credentials and supporting integrations

| Integration | Result | Detail |
|---|---|---|
| Configured review model | PASS | `hackclub` provider with `deepseek/deepseek-v4-flash` returned a live response. |
| Configured vision model | PASS | `qwen/qwen3-vl-8b-thinking` returned a screenshot description through `render_page`. |
| Hack Club API key | PASS | Both model access and `web_search` work. |
| GitHub token | PASS | Authenticated-only code search works. |
| OpenRouter key | FAIL (not active) | OpenRouter `/api/v1/key` returns HTTP 401: `API key expired.` Current `AI_PROVIDER=hackclub`, so normal review/vision calls do not use this key. |
| Shipwrights Dashboard | BLOCKED | Both requests with and without the session cookie return the same Cloudflare HTTP 403 page: `Attention Required!` / `Sorry, you have been blocked`. Cloudflare rejects this machine before the API evaluates the cookie, so the session itself cannot be validated here. |
| Slack bot token | PASS | `auth.test` succeeds. |
| Slack Socket Mode app token | PASS | `apps.connections.open` succeeds; returned URL was not printed or used. |
| Slack configured-channel history | PASS | `conversations.history` and `conversations.replies` both succeed. |
| Slack display-name resolution | PASS | After adding `users:read`, `users.info` succeeds and reconstructed thread history can use display names. |
| Local `remember` / `forget` tools | PASS | Tested against a temporary memory file; production memory was untouched. |
| Typst PDF generation | PASS | Existing real compilation test passed. |
| Chromium / ffmpeg / ffprobe / Typst executables | PRESENT | All required executables resolve on PATH. |

## Not executed

- `run_review`: this chat tool wraps the full review pipeline rather than being a
  primitive. It cannot currently get past the Shipwrights Dashboard Cloudflare block.
- Slack message posting, updating, and file upload: these mutate the live workspace.
  Token scopes needed by those paths (`chat:write`, `files:write`) are present, but no
  test message/file was sent.
- Shipwrights claim, review submission, and internal notes: explicitly mutating API
  endpoints and not registered review-agent tools; forbidden without separate human
  sign-off.
- Full video direction/encoding: not an agent-facing review tool. Browser capture and
  vision were exercised, and ffmpeg/ffprobe are installed, but a full artifact job would
  require a completed `ReviewResult` and additional model/encoding work.

## Actions needed

1. Replace the direct `OPENROUTER_API_KEY` if direct OpenRouter use may be enabled later.
   It does not block the current Hack Club provider configuration.
2. Allowlist or otherwise resolve the deployment machine's access at
   `ds.shipwrights.dev`. Retest there; the present Cloudflare block prevents validating
   `SHIPWRIGHTS_SESSION` or running the watcher/review pipeline from this environment.
