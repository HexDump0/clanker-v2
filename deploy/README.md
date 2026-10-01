# Hosting Clanker for other reviewers

## Coolify (clanker.hexdump0.pw)
Coolify already terminates HTTPS with its own proxy, so deploy the repo's `Dockerfile` directly. You do **not** need `docker-compose.yml`
or the Caddyfile in this folder (those are for hosting without Coolify).

1. **DNS:** add an `A` record `clanker.hexdump0.pw` → your Coolify server's IP.
2. **New resource** → your GitHub repo (`HexDump0/clanker-v2`, branch `main`; add a deploy key / GitHub App if it is private) →
   **Build pack: Dockerfile**.
3. **Domains:** `https://clanker.hexdump0.pw`. **Ports Exposes:** `8765`.
4. **Environment variables:** copy everything from your local `.env` (Dashboard session, Slack, OpenRouter, ...), then add:
   ```
   EXTENSION_API_ENABLED=true
   EXTENSION_API_HOST=0.0.0.0
   EXTENSION_API_TRUST_PROXY=true
   VIDEO_MUSIC_ENABLED=false
   ```
   Optional: `EXTENSION_REVIEWS_PER_USER_PER_DAY`, `EXTENSION_REVIEWS_PER_DAY`, `EXTENSION_ALLOWED_USERS` (see below).
5. **Persistent storage:** add a volume mounted at `/app/data` (results, videos, PDFs, review budget, watcher state). Without it, every
   redeploy wipes them.
6. **Health check:** path `/healthz`, port `8765`.
7. **Stop your local `uv run clanker run` before the first deploy.** Two running copies would both watch the queue and post to Slack twice.
8. Deploy, then check `curl https://clanker.hexdump0.pw/healthz` → `{"ok": true}`.

Things to know:
- The server's own dashboard login (`SHIPWRIGHTS_SESSION`, and `STARDANCE_SESSION`) is a session that **expires** (yours expires
  2026-10-27). When it does, the watcher and reviews stop with auth errors. Update the variable in Coolify and redeploy/restart.
- The hosted server starts with an empty `data/`: reviews you ran locally won't appear in the extension unless you copy your local
  `data/` into the volume. `WATCHER_EMIT_BACKLOG=false` means it will not flood Slack with the existing queue on first start.


The extension talks to Clanker's API. Locally that is `http://127.0.0.1:8765`; hosted it is an HTTPS URL.

## 1. Run it (Docker + Caddy, automatic HTTPS)
1. Point a DNS name at the server (e.g. `clanker.example.com`).
2. Fill in `../.env` as usual. **All Dashboard calls the server makes (watcher, reviews, Slack) use the credentials in this `.env`.**
   Reviewers' own tokens are only ever *validated* (one read-only Dashboard call) and used to know who they are.
3. `echo "CLANKER_DOMAIN=clanker.example.com" > .env.deploy && docker compose --env-file .env.deploy up -d --build`
4. Check: `curl https://clanker.example.com/healthz` → `{"ok": true}`.

Settings worth setting in `.env` (all optional; see `.env.example`):
- `EXTENSION_REVIEWS_PER_USER_PER_DAY` (default 10) and `EXTENSION_REVIEWS_PER_DAY` (default 100): review requests cost money. `0` = unlimited.
  Usage is saved in `data/extension_usage.json`, so restarts don't reset it.
- `EXTENSION_ALLOWED_USERS`: comma-separated dashboard user ids / Slack ids / Slack usernames. Empty = any validated Dashboard user.

What the API does for safety: validates every token against the Dashboard, caches good tokens 5 min and bad ones 1 min, throttles a client
IP after 20 failed logins/min (so strangers can't make the server hammer the Dashboard), answers 403 to people not on the allow-list, and
records who gave each label / asked for each review (shown in Slack and stored with the result).

## 2. Build the extension for your URL
```
cd ../extension
API_URL=https://clanker.example.com ./build.sh       # writes ../dist/clanker-chrome.zip and clanker-firefox.xpi
```
This bakes the URL in as the default API address and adds it to the extension's host permissions. Reviewers can still change it under
Clanker → Settings.

## 3. Get it to reviewers
- **Firefox** only installs signed add-ons. Unlisted signing on addons.mozilla.org is free:
  `AMO_API_KEY=… AMO_API_SECRET=… API_URL=https://clanker.example.com ./build.sh --sign` (keys from the AMO developer hub → API keys).
  Send reviewers the signed `.xpi` from `../dist/`.
- **Chrome**: upload `../dist/clanker-chrome.zip` to the Chrome Web Store (unlisted is fine, one-time $5 fee), or have reviewers use
  "Load unpacked" on the `extension/` folder.

## Known limits
- One server instance: results are JSON files and review jobs/cooldowns live in memory (a restart forgets running jobs and cooldowns).
- Reviews requested from the extension count against the budget even if they fail.
