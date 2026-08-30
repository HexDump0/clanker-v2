# Shipwrights Dashboard - Reverse-Engineered API Reference

Base URL: `https://ds.shipwrights.dev`
Stack: Next.js (App Router, Turbopack) behind Cloudflare. All dashboard data goes through
JSON REST endpoints under `/api/v1/` (plain `fetch`, no Next server actions for cert ops).
The docs pages reference host `dash.shipwrights.dev`, but `ds.shipwrights.dev` serves the app.

## Auth

### Dashboard session (what the review bot uses)
Cookie: `session=<JWT>` (optionally `last-workspace=stardance`).
The JWT payload embeds the user object: `id` (`SW-XXXX`), `slackId`, `email`,
`slackUsername`, `globalRoles`, `sessionId`, `exp`. Send it as a `Cookie` header.

### Ingestion API (workspace -> Shipwrights direction)
Two headers on every request:
```
x-api-key: sw_live_...
x-workplace-id: swwp_...
```
API keys are created in Settings -> Configuration -> API Keys.

Stardance workplace: `slug = "stardance"`, `id = "swwp_30863f4b09a440008dcd65564688c9e2"`.

Errors: `{"error": "..."}` with 401 (bad/missing auth), 403 (missing permission),
404 (unknown route/cert).

---

## Reviewer endpoints (session auth) - the bot's toolbox

### List certifications
`GET /api/v1/workplaces/{slug}/certifications?page=1&status=PENDING&q=&aiType=`

| Param | Values |
|---|---|
| `page` | 1-based |
| `status` | `PENDING`, `IN_REVIEW`, `APPROVED`, `REJECTED`, `RETURNED` (omit = all) |
| `q` | free-text search |
| `aiType` | AI-detected project type: `Web App`, `CLI`, `Hardware`, `Other`, `Extension`, `Chat Bot`, `Android App`, `iOS App`, `Desktop App (Linux)`, `Desktop App (Windows)`, `Desktop App (macOS)`, `Minecraft Mods`, `Cargo` |
| `sort` | Comma-separated table sorts such as `date:asc`, `date:desc`, `dev:asc`, `dev:desc` |

Response:
```json
{
  "certs": ["CertSummary..."],
  "total": 210, "page": 1, "pages": 5,
  "canImport": false,
  "stats": {"PENDING": 210, "APPROVED": 1659, "REJECTED": 2807, "RETURNED": 5},
  "avgWait": 763582,
  "oldest": {"id": "...", "ageSecs": 3600009},
  "aiEnabled": true,
  "aiTypes": ["Web App", "..."],
  "aiTypeCounts": {"Web App": 33}
}
```

`CertSummary` fields: `id, workplaceId, externalId, idempotencyKey, submitterSlackId,
submitterUsername, submitterName, projectName, projectType, shipType, description,
aiDeclaration, aiType, aiIndexState (DONE/...), aiIndexError, aiIndexedAt, updatedProject,
demoUrl, repoUrl, readmeUrl, devTime ("11h 21m"), status, claimerId, claimedAt, claimer,
internalNotes, proofVideoUrl, aiSummary, hackatimeProjects[], returnReason, returnedAt,
yswsPickedUp, createdAt, updatedAt, _count.reviews`.

### Certification detail
`GET /api/v1/workplaces/{slug}/certifications/{certId}`

All summary fields plus: `submitterAvatar, reviews[], attempts[], activeEvents[],
feedbackRequired, proofVideoRequired, feedbackTemplatesEnabled, aiEnabled,
viewerIsClaimer, viewerIsGlobalAdmin, canReport`.

`reviews[]` contains reviews for the current attempt and may be empty on a pending
resubmission. The complete history is in `attempts[]`, ordered oldest-first. Each attempt
contains `id, externalId, projectName, status, createdAt, returnReason, returnedAt,
reviews[]`. Historical attempt reviews currently omit their own `id` and `certId`, so
clients must not require those two fields.

`reviews[]` entry:
```json
{
  "id": "...", "certId": "...", "reviewerId": "...", "reviewerSlackId": "U...",
  "verdict": "APPROVED", "comment": "...", "createdAt": "...",
  "reviewer": {"displayName": null, "slackUsername": "..."}
}
```

Reviewer objects may also include `slackId` and `slackAvatar`.

### GitHub data (cached server-side)
`GET /api/v1/workplaces/{slug}/certifications/{certId}/github`
```json
{"status": "ok", "cached": true, "data": {
  "repo": {"fullName": "...", "url": "...", "createdAt": "...", "language": "..."},
  "commits": [{"sha": "...", "shortSha": "...", "message": "...", "authorName": "...",
               "authorLogin": "...", "date": "...", "url": "..."}]}}
```

### README (cached server-side)
`GET /api/v1/workplaces/{slug}/certifications/{certId}/readme`
```json
{"status": "ok", "cached": true, "markdown": "# ..."}
```

### Claim / unclaim [MUTATING]
`POST /api/v1/workplaces/{slug}/certifications/{certId}/claim`
Body: `{"unclaim": false}` (`true` releases the claim).
Moves status `PENDING`/`RETURNED` -> `IN_REVIEW`, assigns you as claimer.
Response includes updated `status`, `claimerId`, `claimer`.

### Submit review [MUTATING - bot must not call without human sign-off]
`POST /api/v1/workplaces/{slug}/certifications/{certId}/review`
Body: `{"verdict": "APPROVED" | "REJECTED", "comment": "..."}`
UI gate: only when `status === "IN_REVIEW"` and (`viewerIsClaimer` || `viewerIsGlobalAdmin`).
Stardance has `feedbackRequired: true`, so an empty comment is rejected client-side
(enforce server-side too, presumably).

### Internal notes [MUTATING]
`PATCH /api/v1/workplaces/{slug}/certifications/{certId}`
Body: `{"internalNotes": "..."}`

`internalNotes` is returned by certification list/detail reads. It is private reviewer
context and must not be copied into submitter-facing feedback or public artifacts.

### Report certification to Fraud Squad [MUTATING]
`POST /api/v1/workplaces/{slug}/certifications/{certId}/report`

Observed in the current Dashboard frontend when detail response `canReport` is true.
Request body/response semantics have not been safely exercised. Do not call without an
explicit, human-confirmed reporting workflow.

### Proof video upload (3-step, Cloudflare R2)
1. `GET .../certifications/{certId}/upload?filename=x.mp4&contentType=video/mp4`
   -> `{"uploadUrl": "<presigned R2 PUT URL, 1h expiry>", "publicUrl": "..."}`
2. `PUT <uploadUrl>` with raw bytes, header `Content-Type: video/mp4`
3. `POST .../certifications/{certId}/upload` body `{"url": "<publicUrl>"}` [MUTATING]
Delete: `DELETE .../certifications/{certId}/upload` [MUTATING]

### Feedback templates (canned review comments)
- `GET /api/v1/workplaces/{slug}/feedback-templates`
  -> `{"shared": [...], "mine": [...], "reviewerSlackUsername": "..."}`
- `POST /api/v1/workplaces/{slug}/feedback-templates` [MUTATING]
  Body: `{"title": "...", "body": "...", "shared": false}`
- `DELETE /api/v1/workplaces/{slug}/feedback-templates/{templateId}` [MUTATING]

Template bodies support placeholders: `{SubmitterUsername}`, `{SlackUsernameOfReviewer}`.

### Leaderboard
`GET /api/v1/workplaces/{slug}/certifications/leaderboard?range=daily|weekly|all`
```json
{"range": "weekly", "entries": [
  {"memberId": "s:U...", "name": "...", "avatar": "...",
   "total": 830, "approved": 284, "rejected": 546}]}
```

### Workplace info
`GET /api/v1/workplaces/{slug}`
-> id, name, slug, startDate/endDate, contract info, maintenanceMode, etc.

### AI index status
`GET /api/v1/workplaces/{slug}/ai/status`
```json
{"enabled": true,
 "totals": {"total": 4681, "done": 4681, "inProgress": 0, "failed": 0, "notIndexed": 0},
 "byStatus": {"APPROVED": {...}, "PENDING": {...}}}
```

---

## Admin / settings endpoints (exist, but 403 for a plain reviewer session)

All under `/api/v1/workplaces/{slug}/`:
- `GET/PATCH /` (workplace settings update)
- `GET /logs?cursor=&action=&limit=50` (audit log, cursor pagination)
- `POST /certifications/bulk` body `{"certs": [...]}` (CSV import)
- `GET/PUT /cert-settings`, `POST /cert-settings/test-webhook`
- `GET/PUT /payout-config`
- `GET/PUT /storage-config`
- `GET/PUT /ai-config`, `POST /ai/index`
- `GET/POST /api-keys`, `DELETE /api-keys/{id}`
- `GET/POST /events`, `POST /events/{id}/end`, `POST /events/{id}/distribute`, `DELETE /events/{id}`
- `GET/POST /roles`, `PATCH/DELETE /roles/{id}`
- `GET /api/v1/global/users` (global admin)

## User endpoints
- `PATCH /api/v1/user/css` body `{"css": "..."}`
- `PATCH /api/v1/user/display-name` body `{"displayName": "..."}`
- `GET/POST/DELETE /api/v1/user/addresses`

## Auth endpoints
- `GET /api/v1/oauth/slack` -> 307 to Slack OpenID Connect (`slack.com/openid/connect/authorize`),
  callback: `/api/v1/oauth/slack/callback`
- `GET /api/v1/oauth/hca` -> 307 to Hack Club Auth (`auth.hackclub.com/oauth/authorize`,
  scope `openid basic_info slack_id address verification_status`),
  callback: `/api/v1/oauth/hca/callback`
- `GET /api/v1/auth/webauthn/login` (challenge) + `POST` (assertion) - passkey login
- `GET /api/v1/auth/webauthn/register` (challenge) + `POST` (attestation) - passkey setup
- `GET/DELETE /api/v1/auth/webauthn/keys` - list/remove passkeys
- `GET /api/v1/auth/sessions` - list sessions `{id, userId, ip, ua, createdAt}`
- `DELETE /api/v1/auth/sessions` - **revokes ALL sessions incl. current** ("log out everywhere").
  Verified live: returns `{"ok":true,"revoked":N}`. Do not call unless you mean it.
- `GET /api/v1/auth/logout` - logs out, 307 -> `/`
- `GET /api/v1/health` - exists but 401 even with a reviewer session (internal/uptime use)

## Hidden/undocumented methods (found via OPTIONS)
- `POST /api/v1/workplaces/{slug}/certifications` - manual cert creation (403 for reviewer role)
- Method tables per route:
  - workplace: `GET, PATCH`
  - cert detail: `GET, PATCH`
  - claim: `POST` | review: `POST` | upload: `GET, POST, DELETE`
  - github/readme/leaderboard/logs/ai/status: `GET` only
  - feedback-templates: `GET, POST` (+ `DELETE` on `/{id}`)
  - bulk: `POST` | ingest: `POST` | return: `POST` | approved: `GET`

---

## Public Ingestion API (from /docs, API-key auth)

### Submit a ship
`POST /api/v1/certifications/ingest`
Headers: `x-api-key`, `x-workplace-id`, `Content-Type: application/json`
```json
{
  "id": "12345",
  "projectName": "Hack Club",
  "projectType": "Web App",
  "shipType": "initial",
  "description": "...",
  "aiDeclaration": "...",
  "updatedProject": "...",
  "submittedBy": {"slackId": "U...", "username": "...", "name": "..."},
  "links": {"demo": "...", "repo": "...", "readme": "..."},
  "hackatimeProjects": ["..."],
  "hackatimeId": 123,
  "metadata": {"devTime": 64800}
}
```
Required: `id` (external ID, idempotency), `projectName`, `submittedBy.slackId`,
`links.demo`, `links.repo`, `metadata.devTime` (seconds).
Backfill-only extra fields: `status` (pending/approved/rejected/returned), `feedback`,
`proofVideoUrl`, `returnReason`, `reviewerSlackId`, `createdAt`, `decidedAt`.
-> 201 on success.

### Fetch approved certs (YSWS pull)
`GET /api/v1/certifications/approved` (+ `?refetch=true` to reset pickup flags)
Webhook-delivery workplaces only. Atomically marks returned certs `yswsPickedUp=true`.

### Return a cert
`POST /api/v1/certifications/{certId}/return` body `{"reason": "..."}`
`APPROVED` -> `RETURNED`, re-enters the review queue.

### Decision webhooks (Shipwrights -> workspace)
POST to the configured webhook URL:
```json
{"event": "certification.decision", "timestamp": "...",
 "certification": {"id": "...", "externalId": "...", "projectName": "...",
   "submitterSlackId": "...", "status": "APPROVED", "reviewerComment": "...",
   "proofVideoUrl": "...", "reviewerSlackId": "..."}}
```
Optional secret for signature verification; auto-retries on failure.

---

## Review queue state machine (observed)

```
            claim                    review
PENDING ----------> IN_REVIEW ----------> APPROVED
   ^                   |    \----------> REJECTED
   |                   | unclaim
   \-------------------/
RETURNED --------> IN_REVIEW (re-review; returnReason kept forever)
```

## Bot implementation notes

- Poll `GET .../certifications?status=PENDING&page=N` (50/page, watch `pages`) for the queue.
- `stats` + `avgWait` + `oldest` come free with every list call - good for monitoring.
- Fetch detail + `/github` + `/readme` per cert to build a review packet; both are cached
  server-side so they're cheap.
- Claim before reviewing: review endpoint expects the cert `IN_REVIEW` and you as claimer.
- Stardance config flags (from cert detail): `feedbackRequired: true`,
  `proofVideoRequired: true`, `feedbackTemplatesEnabled: true`, `aiEnabled: true`.
- Verdicts are uppercase: `APPROVED` / `REJECTED`.
- No rate-limit headers observed; still, be polite (serial requests, small delay).
- Session JWT `exp` is ~30 days out; the bot will need a refreshed cookie periodically.
- Do not send the former `clanker/0.1` user agent: live read-only tests on 2026-08-29 found
  that Cloudflare specifically returned 403 for it while ordinary HTTPX, curl, and browser
  request profiles succeeded with the same session. Detect Cloudflare HTML separately from
  application 401/403 authentication errors.
- Do not feed Dashboard `aiSummary` into Clanker's review agent; keep its judgment
  independent. Human-authored `internalNotes`, attempt reviews, and return reasons are
  useful reviewer context subject to the private-output boundary above.

## Stardance admin ship-queue page (alternate watcher source)

`GET https://stardance.hackclub.com/admin/certification/ship?status=pending&sort=newest&page=N`
with the `_stardance_session_4` cookie. HTML only — `?format=json` and `.json` return
HTTP 500 (verified 2026-08-30).

- `In queue` metric (in the `ship-queue__metrics` block) is the pending total; other
  metrics: Oldest waiting, Approval rate, Reviewed this week, Waiting too long.
- Ships are `<tr class="ship-queue__row...">` rows, 25 per page (`limit=25`), newest
  first: `ship-queue__project-title`, `ship-queue__project-id` (`#NNNN`),
  `ship-queue__cell-author` (bare text), `ship-queue__wait-badge` (e.g. `0d`),
  `ship-queue__hours`, and a `status-pill status-pill--<status>` cell. Some cells are
  duplicated for responsive layouts — keep the first occurrence per field.
- Status filter values: `pending | approved | returned | all`. The "Oldest waiting"
  metric tile also links a ship id — it is not a queue row.
- Stardance ship id == Dashboard cert `external_id`; the watcher source
  (`WATCHER_SOURCE=stardance`) reconciles new ships against Dashboard PENDING pages by
  that id before emitting, since the review packet builder needs the Dashboard record.
- Implementation: `src/clanker/stardance.py`; ordinary HTTPX profile, per-request
  `Cookie` header, redirects not followed (expired session = 302).
- Verified 2026-08-30: Dashboard PENDING (42) is a perfect subset of Stardance pending
  (108); the 66 newest Stardance pending ships are missing from the Dashboard (broken
  import, one-directional). `status=approved`/`returned` walks behave oddly page-by-page
  (more unique ids than the `In queue` metric); `status=pending` is consistent and is
  all the watcher uses. `sort=date:desc` is supported on the Dashboard certifications
  endpoint.
- Ship-page redirect probe (2026-08-30): `GET /admin/certification/ship/<id>` 302s to
  `https://ds.shipwrights.dev/stardance/certifications/<cert-uuid>` once the Dashboard
  has imported the ship (cert id = last path segment); ships the Dashboard does not
  know return HTTP 200 with the Stardance review page. The watcher uses this to
  reconcile a new ship with a single Stardance request (one retry after 10s on a miss;
  second miss = "dash down", ship dropped). A redirect to `/login` means the Stardance
  session cookie expired.
