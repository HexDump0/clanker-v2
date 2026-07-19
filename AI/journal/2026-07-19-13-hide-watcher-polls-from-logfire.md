# Hide watcher polls from Logfire

**Date:** 2026-07-19 · **Agent:** Codex (GPT-5) · **Type:** fix

## What was done
- Traced the repetitive pending-certification spans to global
  `logfire.instrument_httpx()` instrumentation.
- Added an OpenTelemetry HTTPX exclusion for Shipwrights pending-queue list requests,
  including every page and either query-parameter order.
- Preserved any operator-provided HTTPX exclusion patterns and avoided duplicates if
  observability setup is called more than once.
- Added tests proving that pending polls are excluded while certification details,
  non-pending lists, and unrelated hosts remain traceable.

## Why / decisions made
- Disabling HTTPX instrumentation entirely would also hide useful GitHub, OpenRouter,
  dashboard-detail, and error spans. A narrow URL filter removes only the high-volume,
  low-value watcher traffic.
- OpenTelemetry's installed HTTPX instrumentation reads
  `OTEL_PYTHON_HTTPX_EXCLUDED_URLS` when instrumentation starts, so the application
  installs the derived filter immediately before `logfire.instrument_httpx()`.

## Files touched
- `src/clanker/config.py` — modified — installs the narrow watcher-poll exclusion.
- `tests/test_config.py` — created — covers filtering and existing-pattern preservation.
- `AI/journal/2026-07-19-13-hide-watcher-polls-from-logfire.md` — created — records the fix.

## Open questions / for the human
- None.

## Next steps
- Restart `clanker run`; the already-running process configured HTTPX instrumentation
  before this exclusion existed.
- Confirm pending poll spans stop appearing while review-related HTTP spans remain.
