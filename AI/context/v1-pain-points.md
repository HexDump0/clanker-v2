# sw-clanker v1 — pain points

Observed issues in the v1 code, ordered roughly by impact. These are facts about v1,
**not** a v2 plan — what v2 does about them is decided by the human, not inferred here.

## Functional gaps

1. **Advisory-only: no claim/submit.** v1 reviews ships but never records verdicts back.
   It talks to a read-only "community dash" proxy, not the real Shipwrights Dashboard
   API (which supports claim + review submit — see [`API.md`](./API.md)). A human still
   does all the clicking.
2. **No structured outputs.** `models.py` defines pydantic result models but they're
   unused. Verdict/PDF recovery works by scraping the agent's message log for a specific
   tool call and hoping the LLM emitted valid JSON.
3. **Three agents crammed into one prompt.** precheck/checks/reviewer are logical stages
   simulated in a single monolithic system prompt + single run. No real separation, no
   cheap-model fast path, no structured handoff between stages.
4. **All state in memory.** Seen-ship dedup, review jobs, Slack thread history vanish on
   restart. Worse: `seen_ids` is seeded on first poll, so ships submitted **while the bot
   was down are never auto-reviewed**.
5. **Sequential reviews.** The watcher awaits each review inline; one slow review delays
   all newer ships.

## Reliability / engineering

6. **Blocking call in the async hot path.** `subprocess.run(typst …)` inside an agent tool
   stalls the whole event loop (web + watcher + slack) for up to 30 s.
7. **Import-time side effects & global singletons.** `dash_client` loads+validates config
   at import; `BrowserManager` module-level singletons; config read piecemeal via
   `os.getenv` scattered across 5+ files instead of one `AppConfig`.
8. **Hidden coupling via contextvar.** `review_generate_pdf` silently depends on
   `current_ship_id` being set by the runner; invoking the agent any other way (e.g.
   Slack chat "review 1234") writes PDFs to anonymous tempfiles that are then unfindable.
9. **Fragile supervision.** `run_all.py` cancels all services on first exception; no
   per-service restart/isolation.
10. **Duplicated watcher logic** between `run_watcher.py` and `run_all.py`.

## Prompt / drift

11. **Prompt/tool drift.** The hardcoded `SYSTEM_PROMPT` advertises tools that don't exist
    (`shipwrights_get_latest_submitted_projects`, `review_fetch_flavortown_project`) and
    mixes "Flavortown"/"Stardance" terminology.
12. **Orphaned prompt pack.** `prompts/00_–07_*.md` (8 files) are never imported by any
    code — two generations of prompts coexist and it's unclear which is authoritative.
13. **Behavior enforced by pleading.** PDF-before-summary is an all-caps "CRITICAL" prompt
    instruction instead of control flow.

## Dead weight & hygiene

14. **Dead code:** root `browser_tools.py` (~521 lines), package `browser_tools.py`,
    `models.py`, the numbered prompt pack, `app.py`, screenshot handling in `stream.py`.
15. **Security nits:** static API key compared with `==` (not timing-safe); unauthenticated
    AG-UI chat at `/`; hardcoded Slack channel IDs; unpinned dependencies.
16. **Misc:** hardcoded token-cost rates unrelated to the actual model; `tempfile.mktemp`;
    f-string logging; vestigial `.gitignore` entries for a DB that doesn't exist.

## What v1 does well (keep the ideas)

- The 13-check review rubric + per-project-type demo guidelines (content is solid — port it).
- Typst PDF reports look great (Hack Club dark theme).
- Slack streaming with tool-call task updates; per-thread conversational memory.
- Dual LLM providers (OpenRouter / Hack Club AI proxy) behind one env var.
- Logfire observability end-to-end.
- Docker + GHCR publish pipeline.
