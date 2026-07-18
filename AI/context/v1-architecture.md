# sw-clanker v1 — architecture (the thing we're rewriting)

Source: `sw-reviewer/` (repo root, read-only). Python 3.13, single asyncio process.

## Entry points

| File | Role |
|---|---|
| `run_all.py` | Production (Docker CMD). Runs web + watcher + slack concurrently via `asyncio.wait(FIRST_EXCEPTION)` — one crash kills everything. |
| `run_web.py` | Web-only (Starlette + uvicorn, `127.0.0.1:7932`). |
| `run_slack.py` | Slack-only (Socket Mode). |
| `run_watcher.py` | Watcher-only; also `--test-ship <id>` single-shot mode. |
| `app.py` | Legacy ASGI entry. |

## The pipeline (what it actually does)

1. **Poll** — watcher GETs the community dash `GET /api/queue?status=pending` every 15 s,
   diffs IDs against an in-memory `seen_ids` set (seeded on first poll).
2. **Announce** — posts "New ship!!" to a Slack channel + a threaded "review running" note.
3. **Review** — one pydantic-ai agent run with a giant system prompt simulating three
   stages (pre-check → 13 checks → verdict). Agent calls tools: dash detail fetch,
   GitHub API (repo/readme/commits/languages/tree/files/releases/code-search),
   URL reachability checks, page-text fetch, Stardance page scrape.
4. **Report** — agent is begged (all-caps in prompt) to call `review_generate_pdf` with a
   JSON blob; a Typst template produces a Hack Club-themed PDF at `data/pdfs/{ship_id}.pdf`.
5. **Publish** — runner **scrapes the run's message log** for the PDF tool call to recover
   verdict/reasoning, edits the Slack parent message with a verdict emoji + summary,
   uploads the PDF to the thread.

**Crucially: v1 never claims or submits anything.** `dash_client.py` has two read-only
GETs (`/api/queue`, `/api/review/{id}`) against a separate "community dash"
(`SW_DASH_BASE_URL`, default `http://127.0.0.1:8000`), which itself proxies Stardance.
The bot is advisory-only: a human Shipwright reads the Slack thread and acts.

By contrast, [`API.md`](./API.md) documents the *real* Shipwrights Dashboard API
(`https://ds.shipwrights.dev`) **with claim + review-submit endpoints** — v2 can
close the loop.

## Modules (`sw_reviewer/`)

- `config.py` — `AppConfig` dataclass + dotenv loader; logfire setup. But several modules
  read `os.getenv` directly, bypassing it.
- `agent.py` — pydantic-ai `Agent` factory; model via OpenRouter or Hack Club AI proxy
  (default `xiaomi/mimo-v2-pro`); tools auto-collected by name prefix (`review_*`,
  `shipwrights_*`). Browser tools NOT registered despite existing on disk.
- `review_tools.py` — 13 httpx-based tools (GitHub, URL checks, page fetch, PDF gen).
- `shipwrights_tools.py` — one tool: `shipwrights_get_ship_cert_details` (dash detail fetch).
- `review_runner.py` — Slack formatting + agent orchestration + message-log scraping
  (mixed concerns in one place).
- `prompts.py` — hardcoded `SYSTEM_PROMPT` string (stale: references 2 nonexistent tools).
- `prompts/*.md` — only 4 files actually loaded: `precheck.md`, `checks.md`, `reviewer.md`,
  `demo_guidelines.md`. The numbered pack `00_–07_*.md` is orphaned (never imported).
- `models.py` — pydantic models for structured output (`PreCheckResult`, `ChecksResult`,
  `ReviewResult`…). **100 % dead code** — agent has no `output_type`.
- `pdf_report.py` — shells out **synchronously** to `typst compile` (blocks the event
  loop up to 30 s).
- `context.py` — `current_ship_id` contextvar: hidden runner→PDF-tool channel.
- `dash_client.py` — read-only dash client; **`load_config()` runs at import time**.
- `history.py` — in-memory Slack thread histories (lost on restart).
- `reviewer_state.py` — in-memory manual-review job store (lost on restart).
- `browser_tools.py` (both root and package versions) — browser-use/CDP screenshot
  toolkit. **Dead code**, unwired, and Docker doesn't even install a browser.
- `interfaces/web.py` — AG-UI chat at `/` (**unauthenticated**), REST under `/api/`
  protected by static key compared with `==`.
- `interfaces/slack/` — bolt Socket Mode app; app_mention in one channel only; streaming
  via `chat_stream`; image attachments supported.

## State

Persistent: only the PDFs on disk (`data/pdfs/`). Everything else (seen ships, jobs,
conversation history) is in-memory → restart loses it, and ships that arrived while the
bot was down are silently skipped (first-poll seeding).

## Deployment

`Dockerfile` (python:3.13-slim + Typst v0.15.0 + fonts, unpinned pip deps) → GHCR via
`.github/workflows/docker.yml`. Env-configured (see `v1-pain-points.md` §config or
`.env` key names). `CMD python run_all.py`.
