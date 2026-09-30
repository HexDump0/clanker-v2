"""Jev questions for one review, plus the code that turns answers into a verdict.

All questions go in ONE request per state (Jev evaluates them in parallel; extra questions
are nearly free). Date/number/URL-shape checks are done in code (see state.code_facts).
"""

from __future__ import annotations

from typing import Any

from typesafe_sdk import Choice, Noul

INVESTIGATION_HINT = (
    " Use `reviewer_investigation` (files and pages an investigator fetched) and "
    "`investigator_findings` when present."
)

PROJECT_TYPES = {
    "web_app": "A website or web application used in the browser.",
    "desktop_app": "An application installed and run on Windows, macOS, or Linux.",
    "cli_tool": "A command-line program run in a terminal.",
    "library": "A package, library, or framework other developers import.",
    "api": "A backend HTTP API or service meant to be called by other programs.",
    "bot": "A Discord, Slack, Telegram, or similar chat bot.",
    "android_app": "An Android mobile app.",
    "ios_app": "An iOS mobile app.",
    "game": "A playable video game.",
    "browser_extension": "A browser extension or add-on.",
    "hardware": "A physical electronics or hardware project (PCB, Arduino, 3D-printed device).",
    "vr": "A virtual reality project.",
    "other": "None of the above.",
}


def build_questions(with_investigation: bool) -> dict[str, Any]:
    hint = INVESTIGATION_HINT if with_investigation else ""
    q: dict[str, Any] = {
        # --- repo / readme -------------------------------------------------------------
        "source_present": Noul(
            instructions=(
                "Does the repository contain the project's actual source code, rather than "
                "only a README, screenshots, binaries, or an empty shell? Judge from "
                "`repo_structure` and `computed_facts.tree_code_file_count`." + hint
            )
        ),
        "readme_matches_repo": Noul(
            instructions=(
                "Do `readme`, the project description in `submission`, and the files in "
                "`repo_structure` all describe the same project?" + hint
            )
        ),
        "readme_boilerplate": Noul(
            instructions=(
                "Is `readme` mainly framework scaffold or placeholder text instead of "
                "project-specific writing?"
            ),
            criteria={
                "true": "Scaffold/template text such as 'This template provides a minimal setup', "
                "'Available Scripts', 'bootstrapped with create-next-app', 'Lorem ipsum', "
                "'your-project' placeholders, or the README is just pasted source code.",
                "false": "The README is written about this specific project.",
            },
        ),
        "readme_substance": Noul(
            instructions=(
                "Does `readme` explain what the project is and how to use, run, or install "
                "it, with more than a one-line description?"
            )
        ),
        "readme_english": Noul(
            instructions=(
                "Is the prose of `readme` (headings, paragraphs, instructions — not code) "
                "written in English, or does it link an English version at the top?"
            )
        ),
        "readme_fully_ai_written": Noul(
            instructions=(
                "Is `readme` completely AI-generated generic copy rather than primarily the "
                "author's own project-specific words?"
            ),
            criteria={
                "true": "Generic marketing-style text with no personal voice, typically "
                "stuffed with emoji and buzzwords, that could describe any similar project.",
                "false": "Project-specific writing; professional structure or a few emoji "
                "alone do not count as AI-written.",
            },
        ),
        "generic_vibe_coded": Noul(
            instructions=(
                "Does the project look like a completely AI-generated generic app with no "
                "design choices or personal touches by the author?" + hint
            )
        ),
        "ai_use_undisclosed": Noul(
            instructions=(
                "Is there concrete evidence of AI-generated code, text, or assets that "
                "`submission` AI declaration does not disclose?" + hint
            )
        ),
        # --- demo ----------------------------------------------------------------------
        "project_type": Choice(
            instructions=(
                "What kind of project is this, judged from `repo_structure`, `readme`, and "
                "the demo (not from the claimed type)?"
            ),
            criteria=PROJECT_TYPES,
        ),
        "demo_format_valid": Noul(
            instructions=(
                "Is the demo link the right kind of demo for this project type?" + hint
            ),
            criteria={
                "true": "Web app: live permanently hosted site. Desktop/CLI: downloadable "
                "build in GitHub Releases. Android: APK in Releases or Play Store. iOS: "
                "TestFlight/App Store. Library: package registry page or repo with install "
                "instructions. API: hosted interactive docs. Bot: invite link or server. "
                "Game: playable build or itch.io page. Extension: store listing or release.",
                "false": "Missing demo, video-only demo, source-only link, a folder in the "
                "repo, or a demo that does not fit the project type.",
            },
        ),
        "demo_works_and_matches": Noul(
            instructions=(
                "Does `demo_render` show a working page of the same project described in "
                "`readme` (not an error, blank page, placeholder, login wall only, or an "
                "unrelated site)?" + hint
            )
        ),
        "has_user_accounts": Noul(
            instructions="Does the project have user sign-up/login or accounts?" + hint
        ),
        "premade_credentials_required": Noul(
            instructions=(
                "Must reviewers use shared or premade demo credentials (for example a "
                "posted username and password) because they cannot create their own "
                "account? API keys for trying API endpoints do not count." + hint
            )
        ),
        "claims_supported": Noul(
            instructions=(
                "Are the main features claimed in `submission` description and `readme` "
                "actually present in the repository or demo?" + hint
            )
        ),
        # --- eligibility / human-only ---------------------------------------------------
        "prior_competition": Noul(
            instructions=(
                "Does the submission or README state that this project was previously "
                "submitted to another hackathon, game jam, YSWS program, or competition?"
            )
        ),
        "previous_feedback_unaddressed": Noul(
            instructions=(
                "Does `attempt_history` show earlier rejections whose requested fixes are "
                "still not addressed in the current submission?" + hint
            )
        ),
        # --- holistic decision ------------------------------------------------------------
        "verdict": Choice(
            instructions=(
                "As an experienced Hack Club Stardance Shipwright reviewer, should this "
                "submission be approved or rejected? Required: public repo with real source; "
                "raw GitHub README URL; README in English, original, explaining what it is "
                "and how to use it; a demo in the correct format for the project type on "
                "allowed hosting (no Google Drive, Colab, Hugging Face, Render/Railway free "
                "tiers, tunnels, localhost, zips or raw source files); reviewers can create "
                "their own account; claims match the code; not a fully AI-written or "
                "generic vibe-coded project; earlier rejection reasons fixed." + hint
            ),
            criteria={
                "approve": "Meets every requirement; only minor improvement suggestions.",
                "reject": "At least one requirement clearly fails and must be fixed.",
            },
        ),
        "approvable": Noul(
            instructions=(
                "Would an experienced Hack Club Stardance Shipwright reviewer approve this "
                "submission as it is now, without requesting any fixes?" + hint
            )
        ),
        "main_reject_reason": Choice(
            instructions=(
                "If this submission had to be rejected, what would be the main reason?" + hint
            ),
            criteria={
                "readme": "README problem (not raw link, boilerplate, too thin, not English, AI-written).",
                "demo": "Demo missing, broken, wrong format, or disallowed hosting.",
                "source": "Repo missing, private, or lacking real source code.",
                "ai_generated": "Project is generic AI-generated / vibe-coded.",
                "auth": "Premade credentials or no way to create an account.",
                "eligibility": "Pre-existing or previously competed project not eligible.",
                "banner_or_media": "Banner or devlog media problem.",
                "none": "No meaningful reason to reject.",
            },
        ),
    }
    return q


def rule_verdict(a: dict[str, Any], facts: dict[str, Any]) -> tuple[str, list[str]]:
    """Compose per-check answers into APPROVE / REJECT / FLAG (mirrors reviewer.md logic)."""
    n = {k: v["noul"] for k, v in a.items() if v.get("type") == "noul"}
    fails: list[str] = []
    flags: list[str] = []

    # Code-decided hard failures.
    if not facts["readme_present"]:
        fails.append("no_readme")
    if not facts["readme_url_is_raw_github"]:
        fails.append("readme_not_raw")
    if not facts["repo_url_is_repo_root"]:
        fails.append("repo_url_not_root")
    if facts["demo_url_rejected_platforms"]:
        fails.append("demo_platform:" + ",".join(facts["demo_url_rejected_platforms"]))
    if not facts["demo_url_present"]:
        fails.append("no_demo")
    if facts["commit_count_in_packet"] == 0:
        fails.append("no_commits")

    # Jev-decided failures (strong signals only).
    if facts["tree_file_count"] and n["source_present"] < 0.3:
        fails.append("no_source")
    if n["readme_boilerplate"] > 0.7:
        fails.append("readme_boilerplate")
    if n["readme_substance"] < 0.3:
        fails.append("readme_thin")
    if n["readme_english"] < 0.3:
        fails.append("readme_not_english")
    if n["readme_fully_ai_written"] > 0.8:
        fails.append("readme_ai")
    if n["demo_format_valid"] < 0.3:
        fails.append("demo_format")
    if facts["demo_rendered"] and n["demo_works_and_matches"] < 0.25:
        fails.append("demo_broken")
    if n["premade_credentials_required"] > 0.7:
        fails.append("premade_creds")
    if n["claims_supported"] < 0.25 or n["readme_matches_repo"] < 0.25:
        fails.append("claims_mismatch")
    if n["generic_vibe_coded"] > 0.85:
        fails.append("vibe_coded")

    # Human-needed situations -> flag (per reviewer.md).
    if a["project_type"]["choice"] == "vr":
        flags.append("vr")
    if n["prior_competition"] > 0.6:
        flags.append("prior_competition")
    if n["has_user_accounts"] > 0.6 and n["premade_credentials_required"] <= 0.7:
        flags.append("auth_needs_human_test")
    if facts["repo_created_before_cutoff"] and not facts["declared_as_updated_project"]:
        flags.append("undeclared_update")

    if fails:
        return "REJECT", fails
    if flags:
        return "FLAG_FOR_HUMAN", flags
    return "APPROVE", []
