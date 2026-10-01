# Fix: CORS headers missing on 404 (extension saw a CORS error for unreviewed ships)

**Date:** 2026-10-01 · **Agent:** Claude Code (Sonnet 5.5) · **Type:** fix

- `GET /api/results/{id}` for a ship with no result raises `web.HTTPNotFound`; exceptions bypassed the middleware's
  `response.headers.update(cors)`, so Chrome reported "No Access-Control-Allow-Origin" instead of a 404 and the panel could not
  offer "Request Clanker review". Middleware now adds the headers to raised `HTTPException`s too. Test added (229 expected).
- Earlier fix (Private Network Access header, entry 13) was needed and worked: the preflight now succeeds.
