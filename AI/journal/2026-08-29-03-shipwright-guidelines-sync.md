# Sync Clanker with the current Shipwright guidelines

**Date:** 2026-08-29 · **Agent:** Codex (GPT-5) · **Type:** fix

## What was done
- Compared the owner-supplied current Shipwright guidelines with Clanker's formal
  review prompt, chat reference prompt, URL policy flags, and the prior July guideline
  sync.
- Updated the existing 13-check rubric without changing its structured/PDF schema.
- Added current rules for prior competition eligibility, open-source completeness,
  Streamlit/slow hosting, auth testing, README/AI/vibe-code handling, banners, updated
  projects, GitHub Actions build artifacts, and current mod distribution.
- Added a separate human reviewer procedure for Stardance banner/devlog checks,
  functional/auth testing, professional feedback, and the required dashboard proof
  video. It explicitly says Clanker's generated finding video is not proof-video
  compliance.
- Extended deterministic URL flags to Streamlit, cloudflared/trycloudflare, and DuckDNS,
  including when a permitted-looking URL redirects to a disallowed host.
- Added regression coverage for the new host flags, redirect handling, and inclusion of
  the current rules in both formal-review and Slack-chat instructions.

## Why / decisions made
- The supplied guideline canvas is treated as the current Stardance source of truth.
  The public `hackclub/shipwrights` pre-screening prompt corroborates many rules but is
  behind the supplied canvas in places (for example, it omits Streamlit and retains an
  older program cutoff).
- Eligibility rules affect the structured verdict; human-only reviewer operations do
  not become fake automated checks. Auth projects are escalated when Clanker cannot
  establish the required OAuth and conventional login interaction test.
- Any `fail` now rejects. Ambiguous evidence uses `warn`/human escalation, which lets
  prior-competition and AI rules express the current guidance without guessing.
- Ordinary suspected undeclared AI is warned/reported rather than automatically
  rejected; clearly AI-written READMEs, AI banners, and completely generic vibe-coded
  projects remain hard failures.
- The existing 13 fields were retained to avoid a needless ReviewOutput/PDF migration;
  the changed policy fits the current checks (`pre_event_commits`, `ai_detection`,
  `repo_link_valid`, `demo_credentials`, and demo checks).
- `sw-reviewer/` remained untouched.

## Files touched
- `src/clanker/prompts/system.md` — modified — state evidence and automation limits.
- `src/clanker/prompts/precheck.md` — modified — open-source, host, and prior-program gates.
- `src/clanker/prompts/checks.md` — modified — sync the 13-check policy.
- `src/clanker/prompts/reviewer.md` — modified — align verdict and escalation logic.
- `src/clanker/prompts/demo_guidelines.md` — modified — sync per-project demo rules.
- `src/clanker/prompts/reviewer_procedure.md` — created — isolate human review duties.
- `src/clanker/review/agent.py` — modified — load the procedure for review and chat.
- `src/clanker/review/models.py` — modified — document new special flags.
- `src/clanker/review/tools.py` — modified — detect new banned hosts and redirects.
- `tests/test_review.py` — modified — cover policy loading and URL detection.
- `AI/journal/2026-08-29-03-shipwright-guidelines-sync.md` — created — this record.

## Open questions / for the human
- The canvas says hosting that "takes a while to load" is unacceptable but gives no
  objective latency threshold. The prompt requires corroborating slow/cold-start
  evidence instead of rejecting on one transient request.
- Clanker cannot itself complete interactive auth testing or record the dashboard-safe
  end-to-end proof video; those remain explicit human steps.

## Next steps
- Run a small adjudicated benchmark slice after deployment because changes to AI/vibe
  and prior-competition policy can materially alter verdict distributions.
- Decide later whether to add a dedicated banner-image capture and interactive auth test
  adapter; do not claim these capabilities until implemented.

## Verification
- `uv run pytest -q tests/test_review.py` → 21 passed.
- Scoped Ruff on all changed Python files → passed.
- `git diff --check` → passed.
- Full suite → 56 passed, 1 unrelated pre-existing failure in
  `tests/test_announcer.py`: the implementation posts an extra `I am alive..` message.
  Full Ruff likewise has the pre-existing F541 on that unchanged line.
