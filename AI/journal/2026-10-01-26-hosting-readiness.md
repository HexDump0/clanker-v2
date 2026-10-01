# Hosting readiness: identity, budget, hardening, deployment

**Date:** 2026-10-01 · **Agent:** Claude Code (Sonnet 5.5) · **Type:** feature

- Human: implement the missing hosting pieces (per-user identity, budget cap, HTTPS, signed packages); all server-side Dashboard calls must
  use the credentials in `.env`. They already did: watcher/reviews/Slack use `.env`; the only use of a caller's token is one read-only
  `get_workplace` to validate it. Nothing here changes that.
- Identity: the session cookie is an HS256 JWT whose payload has `user{id, slackId, slackUsername, displayName, ...}` (+ `exp`). After the
  Dashboard accepts the token, `clanker.identity` reads those claims (never the email). Expired tokens are rejected without a Dashboard call.
- API: validator returns an `Identity`; good tokens cached 5 min, bad ones 1 min; per-IP throttle (20 failures/min, honours X-Forwarded-For
  behind a proxy when `EXTENSION_API_TRUST_PROXY`); optional allow-list `EXTENSION_ALLOWED_USERS` (403); `/healthz` unauthenticated; `/api/me`
  (name + reviews left). Feedback records `by_id/by_name`; review requests record `requested_by`; Slack says "Review requested by X" and
  "(marked by X)". Extension: banner shows who marked wrong; "Review a ship" shows reviews left.
- Budget: `clanker.budget.UsageLimiter`, per user and overall per UTC day, persisted in `data/extension_usage.json` (restart-safe).
  Defaults 10/user and 100/day (0 = unlimited). Charged when a review starts (not for an already-running one, or a cooldown hit).
- Deployment: `deploy/docker-compose.yml` (clanker on an internal port + Caddy for automatic HTTPS), `deploy/Caddyfile`, `deploy/README.md`.
  `extension/build.sh` stages the extension, optionally bakes `API_URL` in as the default API + host permission, and with `--sign`
  signs it for Firefox (AMO unlisted).
- Verified: 254 Python tests (identity/budget/allow-list/throttle/attribution/Slack wording), compose config validates, the build with
  `API_URL` was unzipped and checked, and the Chromium reject E2E still passes. NOT verified: an actual deploy behind Caddy with a real
  domain, AMO signing (no keys here), and the Chrome Web Store upload.
- Still open: single instance only (JSON files + in-memory job state); failed reviews still spend budget; a per-person history/audit page.
