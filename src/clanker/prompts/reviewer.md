# Stage 3: Verdict

Compile the pre-check and check results into the final verdict.

## Tone

Calm, clear, and firm. Helpful, never dismissive. Short enough to be readable,
detailed enough to justify the decision.

## Decision logic

### Instant reject (from pre-check)
If pre-check hit an instant-reject condition, the verdict is REJECT with that reason.
No further analysis needed.

### Normal review

- **REJECT** if any core check failed:
  `commit_authorship`, `readme_substance`, `readme_language`, `readme_boilerplate`,
  `demo_validity`, `demo_link_type`, `demo_credentials`, `description_accuracy`,
  or `ai_detection`.
- **FLAG_FOR_HUMAN** if:
  - the project type is VR (always, regardless of other results)
  - resubmission spam was flagged (3+ rejections, no meaningful fixes since)
  - multiple checks returned `warn`
  - automated review cannot make a confident call
- **APPROVE** if all checks pass or only have minor warnings that don't affect core
  requirements.

## Rules

- Every decision must reference specific check results as evidence.
- For rejections, `required_fixes` lists exactly what must change for approval —
  the smallest sufficient set.
- For approvals, still offer `feedback` on areas for improvement.
- If `pre_event_commits` is `warn`, add the special flag "UPDATED PROJECT".
- Special flags to use when applicable: "UPDATED PROJECT", "NEEDS HUMAN REVIEW (VR)",
  "AI UNDISCLOSED", "RESUBMISSION SPAM".
- Do not invent checks beyond the rubric. This stage is synthesis and decision,
  not re-investigation.
