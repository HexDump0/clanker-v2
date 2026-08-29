# Codebase improvement audit — 2026-08-29

This is a point-in-time technical review, not a replacement roadmap. It compares the
current implementation with the human-requested architecture in
`AI/context/v2-architecture-plan.md` and current upstream guidance.

## Executive summary

The rewrite has already removed several v1 failure modes: the Dashboard client is typed
and mutation-gated, review output is Pydantic-validated, the watcher scans every pending
page, generated PDFs no longer block the event loop, browser/video failures are isolated
from the verdict, and 51 of 52 tests pass.

The most valuable next work is at the trust and workflow boundaries, not another review
feature. In priority order:

1. keep secrets out of Docker build contexts and isolate the untrusted browser;
2. add SSRF-safe outbound fetching and bounded response sizes;
3. replace seen-ID dispatch with durable, idempotent review jobs;
4. put deterministic authorization, concurrency, and spend controls around agent tools;
5. reduce prompt-injection and telemetry-data exposure;
6. restore green quality gates and automate them in CI;
7. tighten the canonical result schema and build a representative eval suite.

## P0 — address before treating the service as hardened production software

### 1. Docker currently receives local secret files in its build context

There is no `.dockerignore`, while the workspace contains `.env` and `.env.old`. The
README recommends `docker build ... .`, so Docker recursively makes those files part of
the build context even though the Dockerfile does not `COPY` them. This is especially
risky with a remote builder and unnecessarily sends `.git`, `data/`, `.venv/`, the v1
reference repository, and other local artifacts as well.

Recommended change: add a deny-by-default `.dockerignore` that admits only
`pyproject.toml`, `uv.lock`, and `src/` (plus the Dockerfile itself implicitly). At a
minimum exclude `.env*`, `.git`, `.venv`, `data`, `sw-reviewer`, caches, tests, AI notes,
and local scripts. Docker documents that the local directory is recursively included in
the context and that `.dockerignore` removes files before the context is sent.

Source: <https://docs.docker.com/build/concepts/context/>

### 2. Submitted pages execute in an unsandboxed browser beside production secrets

`review/browser.py` launches Chromium with `--no-sandbox` and no private-network guard.
The Docker image runs as root and the browser lives in the same process/container as the
Shipwrights session, Slack token, GitHub token, and AI keys. The newer video capture path
does reject non-global hosts and intercept subresources, but it also runs `--no-sandbox`
in the credential-bearing service. DNS checks in application code are useful but do not
replace network isolation.

Recommended change: move all browser capture/rendering into a separate unprivileged
worker/container that receives only public URL + artifact job data. Run Chromium as a
non-root user with its sandbox and an appropriate seccomp profile; give the worker no
Shipwrights/Slack/AI/GitHub secrets; restrict egress from the worker to public HTTP(S).
This is already the isolation boundary described by the project architecture plan.

Playwright explicitly recommends a separate user plus seccomp for crawling untrusted
sites; its root mode disables the Chromium sandbox.

Source: <https://playwright.dev/python/docs/docker>

### 3. Plain HTTP tools expose an SSRF and resource-exhaustion surface

`ReviewTools._web` follows redirects automatically. `check_url()` and
`fetch_page_text()` accept any string beginning with `http://` or `https://`, do not
reject credentials or non-public IPs, do not validate redirect hops, and materialize the
entire response before truncating returned text. The packet automatically renders a
submitter-controlled demo URL through the older unguarded browser path. A malicious ship
can therefore target loopback, RFC1918, link-local/cloud metadata, or very large bodies.

Recommended change: create one outbound URL policy shared by HTTP tools and both browser
paths. Parse strictly; permit only HTTP(S); reject URL credentials and unwanted ports;
resolve all A/AAAA records and require global addresses; disable automatic redirects and
revalidate each hop; stream with compressed and decompressed byte ceilings; cap redirect
count, content types, and timeouts. Back this with egress firewall rules because DNS
rebinding/pinning cannot be solved reliably by a single application-layer lookup.

OWASP recommends validating protocols and resolved IPv4/IPv6 addresses, blocking local
and metadata ranges, and disabling automatic redirect following to prevent validation
bypass.

Source: <https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html>

## P1 — correctness, reliability, privacy, and cost

### 4. The watcher is restart-aware but the review workflow is not durable

`Watcher.poll_once()` writes every pending cert ID to `seen_ids` before its handler has
created or completed any durable work. `run_watcher_service()` then launches an in-memory
task and removes its reference on completion without retrieving its exception. A crash
after the state write can permanently lose the job. A service restart can also leave
detached review tasks alive, and the result, Slack thread timestamp, PDF/video state, and
publication state are not persisted.

The Slack `run_review` tool bypasses the watcher's semaphore, so chat requests can create
unbounded concurrent reviews. The same cert can be reviewed simultaneously by watcher
and chat, racing on identical PDF, video, and work-directory paths and duplicating model
spend and Slack uploads.

Recommended change: implement the SQLite `ReviewJob`/artifact state machine already
specified in the architecture plan. Insert a unique job `(cert_id, review_schema_version,
trigger policy)` transactionally before acknowledging discovery. Use leased workers,
bounded attempts/backoff, stage checkpoints, a Slack outbox/publication key, and one
global concurrency limiter shared by watcher and chat. Persist the canonical packet and
`ReviewResult` before producing artifacts, and resume incomplete stages on startup.

For this single deployment, a small explicit SQLite queue is likely simpler than adding
a workflow platform. If requirements grow, current Pydantic AI also supports durable
execution integrations for Temporal, DBOS, Prefect, and Restate.

Sources:

- <https://docs.python.org/3.13/library/asyncio-task.html>
- <https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/>

### 5. Agent-facing untrusted content lacks a complete control boundary

README text, repository files, rendered page text, web content, Slack messages, and image
attachments are all attacker-controlled inputs. Only the `web_search` tool description
explicitly says results are data rather than instructions. An indirect prompt injection
can bias a formal verdict, induce excessive tool calls, invoke the chat agent's costly
`run_review` tool, or poison its persistent `remember` store.

The formal reviewer is read-only and advisory, which limits blast radius, but review
integrity and cost are still material. The chat bot responds in any channel it joins,
does not enforce a user/channel allowlist, routes review commands through the LLM, and
has no per-user rate limit. This also differs from the architecture plan's deterministic
`review <ID>` command parser.

Recommended change:

- label every external-content block and tool return as untrusted data, with a global
  instruction never to follow commands found inside it;
- parse explicit review commands in application code, validate a UUID/dashboard URL,
  authorize the channel/user, and enqueue the durable job without an LLM router;
- make model-requested actions pass a policy function that sees the original user intent,
  not only the tool arguments; keep mutating Dashboard tools unavailable;
- restrict `remember`/`forget` and sensitive/costly tools by channel/user and require an
  explicit user turn, not an instruction embedded in fetched content;
- add per-user/cert cooldowns plus `UsageLimits` for requests, tool calls, tokens, and
  cost; the framework default request limit is currently 50 and no tighter limits are
  passed here;
- add adversarial fixtures for README, webpage, file, image, and Slack-thread prompt
  injection. Prompt text and classifiers are defense-in-depth, not proof of safety.

Sources:

- <https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html>
- <https://pydantic.dev/docs/ai/api/pydantic-ai/usage/>

### 6. Production tracing may export private content without scrubbing

`configure_observability()` calls `logfire.instrument_pydantic_ai()` with content
enabled. When a Logfire token is configured, agent traces can include complete
submission packets, repository/page content, Slack thread histories, memory, attachment
content, tool arguments/results, and model output. This data can involve minors and
private Slack conversations.

Logfire's current documentation says its normal scrubber is deliberately disabled for
LLM message attributes. Recommended default: use `include_content=False` in production,
retain timing/usage/status metadata, and make full-content capture an explicit,
short-lived debug mode with documented access, retention, and consent. Also avoid tokens
or credentials in observed URLs and define what submission/Slack data may leave the
deployment.

Source: <https://pydantic.dev/docs/logfire/instrument/scrubbing/>

### 7. Slack output does not escape or bound untrusted text

`Announcer` inserts project names, project types, descriptions, model reasoning, and
model flags directly into `mrkdwn`. Slack treats `<`, `>`, and `&` as control characters;
manual `<@U...>`, `<!subteam^...>`, and `<!here>` forms can notify users or groups.
Submitter/model text can therefore create unwanted mentions or links. Section text also
has a 3,000-character maximum, but descriptions and result strings are not capped before
posting, so a large input can make the announcement fail after the watcher has already
marked the cert seen.

Recommended change: centralize Slack-safe rendering. Escape `&`, `<`, and `>` in every
untrusted field; use `plain_text` wherever formatting is unnecessary; set `verbatim`
appropriately; validate and separately construct intentional links/mentions; truncate
each field to Slack's documented limits; disable link/media unfurls for submitted URLs
unless wanted. Add tests containing mention syntax, angle brackets, long Unicode, and
over-limit descriptions.

Source: <https://docs.slack.dev/messaging/formatting-message-text/>

### 8. The canonical result is type-valid but not yet a durable review contract

`ReviewOutput` validates field shapes but has no schema version, result/packet identity,
model/provider metadata, confidence or human-review signal, or structured evidence on
each failed/warned rubric check. It also does not enforce cross-field invariants such as
`instant_reject => REJECT + reason`, required fixes on rejection, or consistency between
verdict and check outcomes. The output is never persisted, so a PDF/video retry requires
a new paid review and may produce a different verdict.

Recommended change: implement the versioned `ReviewResult` already described in the
architecture plan, with `extra="forbid"`, bounded strings/lists, cross-field validators,
evidence IDs attached to material checks/fixes, packet/content hashes, prompt/schema
version, model/provider, token/cost metadata, and completion time. Persist it before any
artifact stage; make PDF/video pure consumers of that immutable record.

## P2 — engineering leverage

### 9. The repository's advertised quality gates are red

Observed on 2026-08-29:

- `uv lock --check`: pass.
- `uv run pytest -q`: **1 failed, 51 passed**. The announcement test expects two Slack
  posts, while `announce_ship()` now intentionally makes three after the ping split.
- `uv run ruff check src tests`: fails on the unnecessary f-string in
  `Announcer.announce_online()`.
- `uv run ruff check .`: also finds a line-length error in the user's untracked
  `scripts/score_bench.py`; those untracked benchmark files were not modified.
- no tracked GitHub Actions workflow or other CI configuration was found.

Recommended change: repair the tracked lint/test regressions, test the split-ping
behavior directly, and add CI for `uv lock --check`, frozen sync, Ruff, pytest, and a
dependency audit. Add coverage for `service.py`, chat memory/history, duplicate Slack
events, worker cancellation, same-cert concurrency, crash/resume, SSRF redirect chains,
Slack escaping, and artifact publication retries.

### 10. Reduce and continuously audit the dependency surface

`uv tree --outdated` found several available updates, notably Pydantic AI 2.13.0 to
2.35.3. A local `pip-audit` of the installed environment found four known advisories:

- `aiohttp 3.14.1`: PYSEC-2026-3545/3546/3547; fixes are 3.14.2/3.14.3.
- `cryptography 49.0.0`: PYSEC-2026-3552; fixed in 50.0.0. The published issue is a
  PKCS#7 decryption oracle and does not appear reachable in Clanker's own code, but the
  vulnerable package is still unnecessary attack surface for this deployment.

`aiohttp` is not imported by project code, though it may have been added as the Slack
SDK's async runtime extra; confirm and either remove it or raise the minimum to 3.14.3.
The `cryptography` path arrives through the full `pydantic-ai` meta-package's MCP/Google
extras. This app uses OpenAI-compatible/OpenRouter models, so test replacing it with
`pydantic-ai-slim[openai,logfire]` (or just `[openai]` while retaining the existing
direct `logfire` dependency). Official Pydantic guidance recommends the slim package
when only selected providers/integrations are needed.

Do upgrades in automated PRs with the integration/eval suite, not as an untested bulk
refresh; the locked OpenAI dependency also has a new major version.

Sources:

- <https://pydantic.dev/docs/ai/overview/install/>
- <https://osv.dev/vulnerability/PYSEC-2026-3552>
- <https://github.com/aio-libs/aiohttp/security/advisories>

### 11. Turn the current benchmark work into a release gate

The unit suite mostly proves deterministic plumbing. The untracked benchmark scripts
suggest useful work is already happening, but no tracked golden dataset currently gates
prompt/model/provider changes.

Recommended change: curate representative, consent-safe historical cases with human
verdicts and reason labels; weight false approvals separately from false rejections;
track per-check precision/recall, `FLAG_FOR_HUMAN`, schema validity, tool/request count,
cost, latency, evidence quality, and repeatability. Include adversarial prompt-injection,
missing/stale API data, dead demos, auth walls, huge repos, and ambiguous evidence. Run a
cheap deterministic subset in CI and the live-model suite before prompt/model/provider
promotion. Keep the human verdict as a reference label, not unquestionable ground truth.

Pydantic Evals now provides datasets, custom evaluators, confusion matrices, and
precision/recall report evaluators; plain pytest plus the existing benchmark format is
also sufficient if a new framework adds no value.

Source: <https://pydantic.dev/docs/ai/evals/evals/>

### 12. Harden and simplify the container supply chain

After browser isolation, run the remaining service as a non-root user. Pin the Python
base and copied `uv` image by digest, verify the downloaded Typst archive checksum
instead of piping an unauthenticated download directly into `tar`, and consider a
multi-stage build so build tools do not remain in the runtime image. Add a health signal
that distinguishes process-alive from authenticated Dashboard/Slack readiness, and
gracefully drain/cancel workers on shutdown.

Docker recommends digest pinning for reproducibility and `USER` for services that do
not need privileges.

Source: <https://docs.docker.com/build/building/best-practices/>

## Suggested execution order

1. Same day: add `.dockerignore`; repair the tracked test/lint failures; update/remove
   `aiohttp`; decide whether production traces may contain message content.
2. Security slice: one shared SSRF-safe fetch policy, response limits, Slack escaping,
   deterministic Slack command authorization, global concurrency/usage limits.
3. Reliability slice: SQLite jobs, persisted canonical results, idempotent artifact and
   Slack publication, restart/concurrency tests.
4. Isolation slice: credential-free non-root browser worker with sandbox/seccomp and
   network egress controls.
5. Quality slice: tighten `ReviewResult`, formalize the benchmark/eval dataset, add CI
   and automated dependency updates/audits.

## Decisions for the project owner

- Which Slack channels/users may invoke chat and paid reviews?
- May Logfire store full submission and Slack content, and under what retention/access
  policy?
- Is a local SQLite job store acceptable for the first deployment, as the architecture
  plan proposes?
- Should browser/video remain enabled until worker isolation and SSRF controls land?
- What false-approve, false-reject, cost, and latency thresholds block a model/prompt
  rollout?
