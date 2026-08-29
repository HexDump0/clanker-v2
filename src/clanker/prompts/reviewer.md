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

- **REJECT** if any rubric check is `fail`. A check uses `warn`, not `fail`, when
  evidence or a required human interaction is unresolved.
- **FLAG_FOR_HUMAN** if:
  - the project type is VR (always, regardless of other results)
  - resubmission spam was flagged (3+ rejections, no meaningful fixes since)
  - an authentication flow needs the required interactive OAuth + conventional test
  - prior-competition tracked-time eligibility cannot be established from the packet
  - visible banner/devlog evidence raises a material unresolved AI/content concern
  - multiple checks returned `warn`
  - automated review cannot make a confident call
- **APPROVE** if all checks pass or only have minor warnings that don't affect core
  requirements.

## Rules

- Every decision must reference specific check results as evidence.
- For rejections, `required_fixes` lists exactly what must change for approval —
  the smallest sufficient set.
- For approvals, still offer `feedback` on areas for improvement.
- If the project predates June 1, 2026 or was submitted to another YSWS, add the
  special flag "UPDATED PROJECT" whether or not it was correctly declared.
- Special flags to use when applicable: "UPDATED PROJECT", "NEEDS HUMAN REVIEW (VR)",
  "AI UNDISCLOSED", "RESUBMISSION SPAM", "AUTH FLOW NEEDS HUMAN TEST",
  "PRIOR COMPETITION ELIGIBILITY NEEDS HUMAN CHECK", "BANNER NEEDS HUMAN CHECK".
- Do not invent checks beyond the rubric. This stage is synthesis and decision,
  not re-investigation.

## Browser-visible video evidence

For a REJECT or FLAG_FOR_HUMAN result, include up to five `video_evidence` items for
material findings that can be shown on a public web page. Each item contains a stable
short id, the check/category, the exact page URL, the factual finding, and the one-based
`required_fixes` indexes it supports.

Only include evidence you actually observed while reviewing. Do not choose highlight
text, CSS selectors, coordinates, screenshots, camera treatment, or narration. A
separate vision director handles presentation. Omit evidence that cannot be shown on a
public HTTP(S) page. For APPROVE, `video_evidence` may be empty.
