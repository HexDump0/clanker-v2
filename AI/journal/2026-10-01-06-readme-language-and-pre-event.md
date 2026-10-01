# README language + pre-event (undeclared update) rules

**Date:** 2026-10-01 · **Agent:** Claude Code (Opus 5.5) · **Type:** feature

## What was done
- The human asked which rubric checks the first layer skips. Uncovered: README language, README matches repo,
  pre-event commits, commit authorship. A keyword search of the 235 human rejects in the eval found about 0 real rejects for
  any of them. The human chose to add **README language** and **pre-event** ("reject if not marked as an update").
- `first_layer/language.py`: a deterministic README-prose language guess (no model or dependency). It strips code, HTML,
  links and URLs. It counts as English when English stopwords are at least 8% of words. A reject needs positive evidence: one other language's
  stopwords at 12% or more (es/pt/fr/de/it/id/tr/nl/vi/pl), a mostly non-Latin script, or 80+ CJK characters. It is skipped when an
  English version is linked in the first 25 lines, or when there are fewer than 40 words. Reason `readme_not_english`. When it fires,
  `ai_readme`/`readme_thin` are skipped (Jev's judgement of a non-English README is unreliable).
- Pre-event: the packet only has the latest 30 commits, so the evidence step now fetches history from the forge.
  - GitHub: total commits (Link header) and up to 100 commits `until=2026-06-01`. It counts only the owner's (unlinked
    authors count as the owner; template/upstream authors don't).
  - GitLab: the same via `/repository/commits` (all authors count).
  - Rule: **3 or more of the owner's commits before June 1 and the project not declared as an update** → `pre_event_undeclared`.
- Both reasons are wired through labels, the PDF rubric mapping, message phrasings (Shipwright voice), `ORDER`, video
  (a README live scene for language and a card for pre-event), and PDF evidence and code-check rows ("README language", "Project
  history").
- Both new facts are private (not sent to Jev). `report_v2.py` dev/holdout are unchanged.

## Measurements
- Language: 0 of 296 eval READMEs flagged (the lowest English share was 0.081, just above the 0.08 cutoff; it is safe anyway because no foreign
  stopwords were found). There were no non-English READMEs in the eval, so detection is verified only on synthetic es/pt/zh/hi samples.
- Pre-event, using live GitHub history for 282 eval repos (21 unavailable): it fires on 4. Humans rejected 3 of those (for other reasons) and
  approved 1: `thomas-j-vincent/thomas-website`, where all 100+ own commits are from 2025 and the project was not declared. Per the guidelines it should have been
  marked as an update, so this was a human miss. The Jul-30 repo with stray old-dated commits doesn't fire.

## Files touched
- `src/clanker/review/first_layer/{language.py (new),evidence.py,facts.py,rules.py,reviewer.py,report.py}`,
  `src/clanker/review/{reject_message.py,video/template_director.py}`,
  `tests/{test_language_and_history.py (new),test_first_layer.py}`.

## Open questions
- README-matches-repo and commit-authorship are still human-only (they need judgement).
- Gitea/Codeberg history isn't fetched (its API lacks a reliable `until`), so pre-event never fires there.
