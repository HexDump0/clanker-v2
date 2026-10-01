# Coolify deployment (clanker.hexdump0.pw)

**Date:** 2026-10-01 · **Agent:** Claude Code (Sonnet 5.5) · **Type:** decision

- Human will host on Coolify at `https://clanker.hexdump0.pw`. Coolify has its own HTTPS proxy, so the Dockerfile is deployed directly
  (Caddy compose in `deploy/` is only for non-Coolify hosting). Added `EXPOSE 8765` to the Dockerfile and a Coolify section at the top of
  `deploy/README.md` (DNS, Dockerfile build pack, port 8765, env vars incl. `EXTENSION_API_ENABLED/HOST/TRUST_PROXY`, `/app/data` volume,
  `/healthz` health check, stop the local bot first).
- Checked: repo is `github.com/HexDump0/clanker-v2`; `.env`, `data/`, `dist/` are gitignored (no secrets tracked); all `.env` paths are
  relative (`data/...`) so they land in `/app/data`; `docker build --check` passes (full image build not run here).
- Operational gotchas recorded for the owner: `SHIPWRIGHTS_SESSION` expires 2026-10-27 (hosted watcher/reviews then fail until refreshed);
  hosted starts with empty data; never run local and hosted bots together (duplicate Slack posts).
- Built `dist/` with `API_URL=https://clanker.hexdump0.pw` (default API + host permission baked in). Rebuild without `API_URL` for the local default.
- Not done: pushing to GitHub (Coolify pulls from there); an actual Coolify deploy; Firefox signing.
