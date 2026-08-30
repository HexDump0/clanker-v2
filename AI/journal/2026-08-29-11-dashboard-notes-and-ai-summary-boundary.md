# Include reviewer notes and exclude Dashboard AI summaries

**Date:** 2026-08-29 · **Agent:** Codex (GPT-5) · **Type:** decision

## What was done
- Updated the proposed tool scope after owner feedback.
- Confirmed that `internalNotes` is already typed by the Dashboard model but is not exposed
  in the review packet.
- Recorded that Dashboard `aiSummary` must not be included in agent inputs.
- Refined the Dashboard connectivity diagnosis using the owner's successful curl request.

## Why / decisions made
- Reviewer notes, return reasons, attempt history, and prior review comments are valuable
  human context and should be available to the formal review agent.
- Internal notes are private reviewer data. They may inform review reasoning but must never
  be quoted or copied into submitter-facing feedback, PDFs, videos, or public Slack output
  unless a human explicitly chooses to publish them.
- Dashboard-generated AI summaries would anchor Clanker's independent judgment and are
  therefore excluded entirely rather than merely labelled non-authoritative.
- The successful generic curl request, combined with the earlier failure using the explicit
  `clanker/0.1` user agent, indicates that the immediate compatibility fix should begin by
  removing or changing that identifying user agent. Full browser impersonation is not
  currently justified.
- The session token pasted by the owner was not copied into repository files or journal
  content.

## Files touched
- `AI/journal/2026-08-29-11-dashboard-notes-and-ai-summary-boundary.md` — created — mandatory
  record of the owner's data-boundary decision.

## Open questions / for the human
- None required for the revised plan.

## Next steps
- Implement a private reviewer-context section in the packet, exclude `aiSummary`, and add
  output-boundary tests that prevent internal-note text from entering public artifacts.
