# Jev (TypeSafe) as the review decision-maker — research

**Researched:** 2026-09-30. Sources: https://docs.typesafe.ai/llms.txt (models, system-one,
state, primitives, confidence, jev-1.13 jaggedness, coding-agents) and the OpenRouter catalog.

## What Jev is
- A "System One" decision model, not an LLM. It receives a `state` (text/JSON) and typed
  questions: **Choice** (pick one option, with per-option probabilities), **Score** (a rubric level) and
  **Noul** (the probability that a yes/no statement is true). Each answer comes with a calibrated confidence.
- **It cannot generate text or call tools.** It can't write reasoning, required fixes, or feedback.
- API: `POST https://api.typesafe.ai/v1/systemone`, Python SDK `typesafe_sdk`, needs
  `TYPESAFE_API_KEY` from console.typesafe.ai. **Jev itself is not on OpenRouter.** OpenRouter only lists
  `typesafe/jev-router`, a meta-router that picks *another* LLM and a reasoning effort per request
  (variable pricing). It doesn't replace the decision step.
- `jev-1.13.0`: **$0.042 per 1M input tokens, output free**. Limits are 100K tok/s and 40 req/s (subject to
  change). Context is 64k per request, with **32k for state plus the longest question**. Text only.

## Known weak spots that matter for Clanker (from the jaggedness page)
- Date comparison is unreliable, so `pre_event_commits` / event-window checks must be done in code.
- Counting and numbers are unreliable, so commit-authorship ratios, dev-time and similar must be computed in code.
- Accuracy drops as irrelevant state grows, so the packet has to be filtered for each question.
- It is susceptible to adversarial content in the state. READMEs and demo pages are untrusted, so this is a
  real prompt-injection risk.
- It reads instructions literally, so every rubric check needs precise criteria.

## Fit
- Good fit: the 13 rubric checks as Nouls or Choices, the verdict as a Choice over
  APPROVE/REJECT/FLAG, confidence-gated escalation to a human or an LLM, and picking relevant files
  from the repo tree (Choice/Noul over paths) so that code can fetch them.
- Not a fit: investigation (tool loops), and writing the reasoning, fixes, or feedback. Choosing from Dashboard
  feedback templates might partly cover that.
- Production data (see `production-usage-baseline-2026-09.md`) shows the cost is in the agentic
  investigation loop, not the final decision. Jev only pays off if investigation also becomes
  mostly deterministic.

## Eval idea (no drift)
Logfire `pydantic_ai.all_messages` stores the exact packet and tool results each production review
saw. Replay that frozen evidence to Jev, then compare against (a) the human Shipwright verdict on
the *same attempt* (read-only Dashboard GET of the cert's attempts/reviews) and (b) DeepSeek's
verdict. Later attempts that were approved after fixes don't contaminate the labels, because each
attempt is labelled on its own.

## Status
- The `OPENROUTER_API_KEY` in `.env` returns 401 "API key expired". There is no `TYPESAFE_API_KEY`.
