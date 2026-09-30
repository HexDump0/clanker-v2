# Jev decision eval: results (2026-09-30)

Harness: `evals/jev/` (see its README). Data: `data/eval/jev/` (gitignored).

## Setup
- 120 frozen production reviews from 2026-09-12 → 09-25, 40 per DeepSeek verdict. 118 have a
  human verdict on the *same attempt* (read-only Dashboard). **Humans rejected 92/118 (78%).**
- Systems compared:
  - DeepSeek V4 Flash: the production verdict.
  - Jev on the packet only.
  - Jev on the packet plus a Space Bunny investigation (`stealth/space-bunny-alpha`, free,
    Clanker's read-only tools, GitHub reads pinned to the submission-time commit).
- Jev is scored three ways: rule composition, holistic Choice (+ confidence gate), and an "approvable" Noul.

## Results (n=118, 26 human approvals)
| system | approves | false approves | false rejects | flagged | AUC |
|---|---|---|---|---|---|
| DeepSeek agent | 38 | 23 | 6 | 40 | 0.66 |
| Jev packet, P(approve) ≥ 0.2 | 15 | 7 | 18 | 0 | 0.70 |
| Jev + Space Bunny, P(approve) ≥ 0.2 | 16 | 7 | 17 | 0 | 0.67 |
| Jev rules (my rubric composition) | — | 40 | 9 | 9 | 0.57 |
| always reject (baseline) | 0 | 0 | 26 | 0 | — |

- **Nothing predicts the human decision well.** All AUCs are 0.66–0.70, and with only 26 positives the
  uncertainty is about ±0.06, so the systems are statistically indistinguishable.
- **Jev on the packet alone matches DeepSeek**: $0.00026 and 0.7 s per decision, against
  $0.0096 and 56 s for the DeepSeek agent. That is about 37× cheaper and 75× faster, before counting the
  DeepSeek packet-build time.
- The **Space Bunny investigation added no measurable signal** (0.67 vs 0.70). It is free but adds
  p50 26 s / p90 55 s and about 37k input tokens per review.
- Jev's default decision (holistic Choice or Noul at 0.5) rejects nearly everything, which is
  equivalent to always-reject. It needs a tuned threshold. The t=0.2 row is a sweep point, not a validated
  operating point.
- My rule composition (the `reviewer.md` logic) is the worst option. It approves whenever no explicit
  check fails, and the rubric doesn't encode how strictly humans actually treat AI use.

## Why humans reject (from their comments)
The dominant reason is **AI use**. DeepSeek approved 23 attempts that humans rejected, and
about 19 of those were rejected for AI reasons (comments can have several tags): "CSS looks like every other
AI site", "README written with AI", "undeclared AI", and one reviewer cites "max 30% AI". Next come
README detail and demo/executable problems. Clanker's rubric (`checks.md` ai_detection) is much
more lenient than real reviewer practice. **That is the biggest quality gap, and it is independent of the
model.**

## Caveats
- The sample is stratified by DeepSeek verdict (1/3 each), whereas production was about 44/36/20
  approve/reject/flag. The population human reject rate may differ.
- Humans see things the bot doesn't: banner images, proof videos, the actual look of the site.
  Labels come from the first human review, which can lag the bot review by hours to days.
- The thresholds and question wording were tuned by looking at this same set, with no holdout.

## Update: first-layer "confident reject" framing (same day)

The human clarified Clanker's role: it is an automated **first layer**. Everything it doesn't
reject goes to a human, who tests the demo anyway. Its only job is to reject what it can
confidently establish. The metrics are therefore reject precision (humans agree), human-reject recall
(workload removed), and good projects wrongly bounced.

Setup: `evals/jev/questions_reject.py` has 8 yes-means-reject Nouls worded from real reviewer
comments (AI code/CSS over the 30% limit, AI README, thin README, demo not testable, demo broken,
feedback ignored, AI undeclared, not eligible). Code-decided rules cover the raw README link, banned
hosting and a missing README. Jev also gets code excerpts (up to 3 files, pinned to the submission commit,
`evidence.py`). Thresholds were tuned on the dev set (118, stratified). A conservative preset (AI ≥ 0.7,
thin README ≥ 0.9, undeclared ≥ 0.6) was fixed before looking at the holdout. The **holdout** is 157
random reviews from 2026-08-31 → 09-12 (production mix; humans rejected 78%). It was never tuned on.

| holdout (n=157) | rejects | precision | human rejects caught | good bounced (of 35) |
|---|---|---|---|---|
| DeepSeek REJECT verdicts | 55 | 85% | 47/122 (39%) | 8 |
| code rules only | 17 | 94% | 16 (13%) | 1 |
| **code + Jev, conservative** | **71** | **89%** | **63 (52%)** | **8** |
| code + Jev, dev-tuned | 99 | 85% | 84 (69%) | 15 |

- The conservative Jev preset beats DeepSeek: 16 more correct rejects with the same number of wrongly bounced
  good projects. It costs $0.00031/review (vs ~$0.0096) and takes ~0.75 s (vs ~56 s plus packet build).
- On the holdout, the reasons with at least 90% precision were: AI README ≥ 0.6 (98%), AI undeclared (100%),
  demo broken ≥ 0.7 (100%), AI code ≥ 0.6–0.7 (91–93%), and demo not testable ≥ 0.9 (90%). Thin README
  (~80%) and feedback ignored (~80%) are weaker. Thin README caused 4 of the 8 conservative bounces.
- The reject reason matches the human's reason (keyword match) on about 73% of correct rejects.
- Label noise: GitHub READMEs can change between the bot review and the human review, and DeepSeek
  also rejected 5 of the 8 conservative bounces.
- Per-review data: `data/eval/jev/{dev,holdout}/decisions.csv` (gitignored).

## Update: v2 checks (banner, demo code checks, cheap checks, richer AI evidence)

Holdout = 186 random reviews (Aug 31 – Sep 12; humans rejected 143 and approved 43). Thresholds are in
`thresholds_conservative2.json`; nothing was tuned on the holdout.

| holdout | rejects | precision | human rejects caught | good bounced (of 43) |
|---|---|---|---|---|
| DeepSeek | 68 | 87% | 59 (41%) | 9 |
| v1 conservative | 78 | 87% | 68 (48%) | 10 |
| **v2** | **102** | **87%** | **89 (62%)** | **13** |

Per reason on the holdout (fires, precision): ai_code 36 (94%), ai_readme 31 (94%), readme_thin 27
(85%), banner_bad 20 (95%, but 64% on dev), ai_undeclared 14 (100%), readme_not_raw 10 (90%),
demo_broken 10 (90%), needs_api_key 6 (83%), no_source 4 (**50%**, weak on dev too; drop or fix),
demo_is_video 3 (100%), bad_hosting 3 (100%). About 20% of historical banner URLs now return 404
(banners replaced later), so the historical data under-exercises the banner check.

## Reject messages
`src/clanker/review/reject_message.py` builds rejection text that reads like a Shipwright wrote it,
with no model involved. It uses per-reason phrasings modeled on 235 real reviewer comments (greeting,
generic compliment, 1–2 issues inline or up to 3 bullets, "reship", #ask-the-shipwrights). Output is
seeded by cert id so it is stable, and the wording varies between certs. It never signs as a person or
claims anyone tested anything. Samples next to the human comments are in
`data/eval/jev/{dev,holdout}/messages_v2.csv`.
