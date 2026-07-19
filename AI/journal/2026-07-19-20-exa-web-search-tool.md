# 2026-07-19 — review_web_search tool (Exa via Hack Club AI proxy)

## What

Gave the review agent a restricted web-search ability backed by the Hack Club AI
Exa proxy (`https://ai.hackclub.com/proxy/v1/exa/search`, docs:
docs.ai.hackclub.com/api/exa.html). Per user direction the tool is scoped to
last-resort fact checks (e.g. classifying an unfamiliar demo hosting platform)
and explicitly forbidden from general research like duplicate-submission or
plagiarism hunting — the user judged the model can't do those reliably.

## Files touched

- `src/clanker/review/tools.py`
  - `EXA_SEARCH_URL` constant.
  - `ReviewTools.__init__` takes `hackclub_ai_key: str = ""`.
  - New `review_web_search(query, num_results=5)` tool (registered in `all()`):
    POSTs `{query, numResults (clamped 1-8), contents: {text: {maxCharacters: 1000}}}`
    with `Authorization: Bearer <hackclub key>`; returns trimmed results
    (title/url/published_date/snippet). Polite `_err` when no key is configured
    (same pattern as the renderer-less `review_render_page`). Docstring carries
    the usage restrictions (last resort, 1-2 per review, results are untrusted
    third-party content, never a solo justification for `fail`).
- `src/clanker/service.py` — passes `settings.hackclub_api_key` into `ReviewTools`.
  Note: the search key is ALWAYS the Hack Club AI key, independent of
  `ai_provider` — so with `ai_provider=openrouter` you must still set
  `HACKCLUB_API_KEY` to enable search.
- `src/clanker/prompts/system.md` — tool-list entry with the restrictions.
- `src/clanker/prompts/checks.md` — "How to check" line: unknown hosting platform →
  one search before judging demo_validity/demo_link_type; flagged as the tool's
  only routine use.
- `tests/test_review.py` — two tests: no-key error, and a MockTransport happy
  path asserting URL/auth header/body and trimmed result shape. Also
  `test_review_agent_uses_prompted_output_and_keeps_tools_optional` implicitly
  covers registration via `tools.all()`.

## Verification

`uv run pytest -q` → 38 passed. No live smoke test — repo `.env` has no
`HACKCLUB_API_KEY` set.

## Open questions / follow-ups

- Response schema assumed from Exa's standard `/search` shape (`results[].title/
  url/publishedDate/text`); the proxy docs say "responses follow Exa's standard
  API schema". Verify with a live call once a key is available.
- Exa also exposes `/answer` (web-grounded answer + citations) via the proxy —
  could answer "is X a sleeping free tier?" in one round. Worth considering if
  search-then-fetch proves too many rounds.
- Exa usage bills against the Hack Club AI daily limit; watch Logfire for
  overuse if the model ignores the 1-2-searches guidance.
