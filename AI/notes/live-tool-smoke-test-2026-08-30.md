# Live Clanker tool smoke test — 2026-08-30

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
| `get_github_repo_tree` | PASS | Recursive tree returned. |
| `get_github_file_content` | PASS | Requested README file returned. |
| `get_github_releases` | PASS | Releases returned. |
| `search_github_code` | PASS | Matches returned; authenticated code search works. |
| `check_url` | PASS | `example.com` reachable, HTTP 200. |
| `fetch_page_text` | PASS | HTTP 200 and extracted text returned. |
| `render_page` | PASS | Chromium rendered the page and the vision model described it. |
| `fetch_stardance_project` | PASS | Live project 34363 fetched with session cookie; structured summary, 2 devlogs, completeness metadata. |
| `fetch_stardance_devlog` | PASS | Live devlog 27822 fetched with structured output. |
| `check_package` | PASS | PyPI package metadata returned. |
| `web_search` | PASS | Hack Club Exa proxy returned results. |

Result: **15/15 registered review tools pass**.

Note: Stardance project URLs are not Exa-indexed and do not appear in cert
`demo_url`/`repo_url` fields; live URLs can be recovered from the sanitized HAR
archive in `har/`.

## Credentials and supporting integrations

| Integration | Result | Detail |
|---|---|---|
| Configured review model | PASS | `hackclub` provider, `deepseek/deepseek-v4-flash` answered a live ping. It is a reasoning model — a tiny `max_tokens` budget is consumed by reasoning tokens before any content is emitted. |
| Configured vision model | PASS | Described a Chromium screenshot through `render_page`. |
| Hack Club API key | PASS | Both model access and `web_search` work. |
| GitHub token | PASS | Authenticated code search works. |
| Shipwrights Dashboard | PASS | The Cloudflare 403 block seen on 2026-08-29 is resolved. `list_certifications` (50 certs page 1 of 206) and `get_feedback_templates` return JSON 200 with the configured session. |
| Slack bot token | PASS | `auth.test` succeeds. |
| Slack Socket Mode app token | PASS | `apps.connections.open` succeeds; URL not printed or used. |
| Slack configured-channel history | PASS | `conversations.history` succeeds. |
| OpenRouter key | FAIL (not active) | `/api/v1/key` still HTTP 401: `API key expired.` `AI_PROVIDER=hackclub`, so normal review/vision calls do not use it. |

## Not executed

- `run_review` full pipeline: now unblocked by the Dashboard access fix, but not run
  (costs model tokens and would be best observed by the human).
- Slack writes/uploads, Shipwrights claims/review submissions/notes: mutating,
  forbidden without explicit human sign-off.
- Full video direction/encoding pipeline: browser capture, vision, and ffmpeg presence
  were exercised; a full artifact job needs a completed `ReviewResult`.

## Actions needed

1. Replace `OPENROUTER_API_KEY` if direct OpenRouter use may be enabled later.
