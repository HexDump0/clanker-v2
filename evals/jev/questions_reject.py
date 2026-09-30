"""First-layer "confident reject" questions for Jev.

Clanker's job as the automated first layer: reject only what it can confidently establish;
everything else passes to a human, who tests the demo anyway. Each question below maps to a
reject reason human Shipwrights actually use (wording taken from their review comments),
and each is phrased so that YES means "reject for this reason".
"""

from __future__ import annotations

from typing import Any

from typesafe_sdk import Choice, Noul

# Reason id -> short human-facing fix text (for the Slack/PDF message).
REASONS = {
    "ai_code": "The code/CSS looks mostly AI-generated (over the 30% AI limit). Rewrite the "
    "styling and core parts yourself and add your own features.",
    "ai_readme": "The README reads as AI-written. Rewrite it yourself: what it is, how you "
    "built it, how to use it.",
    "readme_thin": "The README is too thin. Explain what the project is, its features, how to "
    "use/run it, and how and why you built it.",
    "demo_not_testable": "The demo link doesn't let a reviewer actually try the project (it "
    "must be a live site, downloadable build, store/extension package, or bot invite).",
    "demo_broken": "The demo doesn't load or shows an error/blank page.",
    "feedback_ignored": "The previous rejection's requested changes haven't been made.",
    "ai_undeclared": "AI use is visible but not declared in the AI declaration.",
    "not_eligible": "The project isn't eligible (e.g. a school assignment).",
    # Code-decided:
    "readme_not_raw": "Set the README link to the raw.githubusercontent.com URL of the README.",
    "bad_hosting": "The demo is on a disallowed host (Render/Railway/Streamlit/tunnels/Drive/"
    "Colab/Hugging Face/localhost). Host it on permanent hosting.",
    "no_readme": "The repository has no README.",
}

AI_LOOK = (
    "Typical signs: CSS that 'looks like every other AI-made site' — CSS-variable color "
    "palettes, gradient hero sections, glassmorphism cards, uniform '/* ===== Section ===== */' "
    "comment banners, emoji in comments, over-explained step-by-step comments, perfectly "
    "consistent naming and structure throughout, generic landing-page sections."
)


def build_reject_questions() -> dict[str, Any]:
    return {
        "ai_code": Noul(
            instructions=(
                "Judging from `code_excerpts` and the demo screenshot description in "
                "`demo_render`, is most of this project's code or styling AI-generated rather "
                "than written by the author?"
            ),
            criteria={
                "true": "Mostly AI-generated. " + AI_LOOK,
                "false": "Looks hand-written: personal or inconsistent style, beginner "
                "mistakes, unusual choices, sparse or informal comments. Also false when "
                "`code_excerpts` is empty.",
            },
        ),
        "ai_readme": Noul(
            instructions="Was `readme` written with AI tools rather than by the author?",
            criteria={
                "true": "Generic marketing tone, emoji section headers (e.g. '✨ Features', "
                "'🚀 Getting Started'), buzzwords, polished boilerplate sections with no "
                "personal voice or real development story.",
                "false": "The author's own words: personal voice, specific details, informal "
                "or imperfect writing. A clean structure alone is not AI.",
            },
        ),
        "readme_thin": Noul(
            instructions=(
                "Is `readme` missing the basics a reviewer needs: what the project is, its "
                "features, and how to use or run it?"
            ),
            criteria={
                "true": "Empty, one or two lines, only a title/link, or only a feature list "
                "with no usage or explanation.",
                "false": "Explains what it is and how to use it, even briefly.",
            },
        ),
        "demo_not_testable": Noul(
            instructions=(
                "Does the demo link in `submission` fail to let a reviewer actually try this "
                "project?"
            ),
            criteria={
                "true": "It points to the repo/README/source instead of the app, an itch.io "
                "page with no playable or downloadable build, a browser extension with no "
                "store listing or packaged release, a bot with no invite/server/channel, a "
                "video only, or a page unrelated to the project.",
                "false": "A live website of the project, a release with a runnable build, a "
                "store/registry listing, or a bot invite. Also false when unsure.",
            },
        ),
        "demo_broken": Noul(
            instructions=(
                "Does `demo_render` show that the demo fails to load: an HTTP error, a 404 or "
                "error page, a blank page, or a deployment/placeholder page?"
            )
        ),
        "feedback_ignored": Noul(
            instructions=(
                "Was this project rejected before (see `attempt_history`) and do the "
                "reviewer's requested changes still appear unaddressed now? "
                "`computed_facts.commits_after_last_rejection` counts new commits since the "
                "last rejection."
            ),
            criteria={
                "true": "A previous rejection asked for specific changes and the current "
                "README/code/demo still shows the same problem, or there are no new commits.",
                "false": "No previous rejection, or the requested changes appear to be made.",
            },
        ),
        "ai_undeclared": Noul(
            instructions=(
                "Is there clear evidence of AI-generated code or text while the AI "
                "declaration in `submission` says no AI was used?"
            )
        ),
        "not_eligible": Noul(
            instructions=(
                "Does the submission say this is a school assignment or class project, or "
                "otherwise clearly ineligible for a Hack Club program?"
            )
        ),
        "main_reason": Choice(
            instructions="What is the single biggest problem with this submission?",
            criteria={
                "ai_code": "Code/styling mostly AI-generated.",
                "ai_readme": "README written by AI.",
                "readme_thin": "README too short or missing usage.",
                "demo": "Demo missing, broken, or not testable.",
                "feedback_ignored": "Previous rejection feedback not addressed.",
                "none": "No clear problem.",
            },
        ),
    }


JEV_REASONS = (
    "ai_code", "ai_readme", "readme_thin", "demo_not_testable", "demo_broken",
    "feedback_ignored", "ai_undeclared", "not_eligible",
)


def reject_decision(
    answers: dict[str, Any], facts: dict[str, Any], thresholds: dict[str, float]
) -> tuple[str, list[str]]:
    """REJECT only when code proves it or a Jev reason clears its threshold; else PASS."""
    reasons: list[str] = []
    if not facts["readme_present"]:
        reasons.append("no_readme")
    if facts["readme_present"] and not facts["readme_url_is_raw_github"]:
        reasons.append("readme_not_raw")
    if facts["demo_url_rejected_platforms"]:
        reasons.append("bad_hosting")
    for key in JEV_REASONS:
        t = thresholds.get(key)
        if t is None:
            continue
        if key == "demo_broken" and not facts["demo_rendered"]:
            continue
        if key == "feedback_ignored" and not facts["previously_rejected"]:
            continue
        if answers[key]["noul"] >= t:
            reasons.append(key)
    return ("REJECT" if reasons else "PASS"), reasons
