"""First-layer "confident reject" questions for Jev.

Clanker's job as the automated first layer: reject only what it can confidently establish;
everything else passes to a human, who tests the demo anyway. Each question below maps to a
reject reason human Shipwrights actually use (wording taken from their review comments),
and each is phrased so that YES means "reject for this reason".
"""

from __future__ import annotations

import re
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
    # v2 code/vision-decided:
    "banner_default": "Set a project banner: a screenshot of your project in action.",
    "banner_bad": "Your banner must be a screenshot of your project in action (not code, a "
    "logo, AI art, or an unrelated image). Change it in project settings.",
    "demo_is_video": "The demo link must let reviewers try the project, not a video.",
    "demo_is_repo": "The demo link points at the repository. Link the live site, a release "
    "build, or the package/store page instead.",
    "missing_build": "There's no downloadable build in your GitHub Releases. Upload the "
    "executable/APK/binary to a release and link it as the demo.",
    "itch_no_build": "Your itch.io page has no downloadable or browser-playable build.",
    "bot_link_invalid": "A bot's demo link must be a server/channel invite where reviewers can "
    "use the bot.",
    "no_source": "The repository doesn't contain the project's source code.",
    "untitled": "Your project is named 'untitled'. Give it a real name.",
    "needs_api_key": "Reviewers can't test it without their own API key. Include a working "
    "key/proxy (e.g. Hack Club AI) so the demo works out of the box.",
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
        "project_type": Choice(
            instructions=(
                "What kind of project is this, judged from `readme`, `repo_structure`, and the "
                "demo (not from the claimed type)?"
            ),
            criteria={
                "web_app": "A website or web app used in the browser.",
                "desktop_app": "An application installed on Windows/macOS/Linux.",
                "cli_tool": "A command-line program.",
                "library": "A package/library other developers import.",
                "api": "A backend HTTP API.",
                "bot": "A Discord/Slack/Telegram chat bot.",
                "android_app": "An Android app.",
                "ios_app": "An iOS app.",
                "game": "A playable video game.",
                "game_mod": "A mod for an existing game.",
                "browser_extension": "A browser extension or userscript.",
                "hardware": "A physical electronics/hardware or 3D-printed project.",
                "other": "None of the above.",
            },
        ),
        "needs_api_key": Noul(
            instructions=(
                "Does the project require the reviewer to supply their own API key, token, or "
                "paid account before the main feature works (no key or proxy is included)?"
            ),
            criteria={
                "true": "README/code asks the user to paste their own OpenAI/Gemini/other key "
                "or set env vars before it works, and the demo has no built-in key or proxy.",
                "false": "Works out of the box, uses a bundled key/proxy, or needs no key.",
            },
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
    "feedback_ignored", "ai_undeclared", "not_eligible", "needs_api_key",
)

VIDEO_HOSTS = re.compile(r"(^|\.)(youtube\.com|youtu\.be|vimeo\.com|loom\.com|streamable\.com)$")
BOT_HOSTS = re.compile(r"(^|\.)(slack\.com|discord\.gg|discord\.com|discordapp\.com|t\.me|telegram\.me)$")
BUILD_EXT = {
    "desktop_app": (".exe", ".msi", ".dmg", ".zip", ".appimage", ".deb", ".rpm", ".tar.gz", ".pkg"),
    "android_app": (".apk", ".aab"),
    "cli_tool": (),
}
BAD_BANNERS = {"code_screenshot", "logo_or_text", "ai_generated_art", "unrelated"}
# Anything suggesting a downloadable or browser-embedded build on the itch.io page.
ITCH_PLAYABLE = re.compile(
    r"download|run game|play in browser|launch|fullscreen|loading|embed|canvas|game window|"
    r"\.zip|\.exe|\.apk",
    re.I,
)


def _host(url: str) -> str:
    m = re.match(r"https?://([^/:?#]+)", url or "")
    return m.group(1).lower() if m else ""


def _hosted_bot(answers: dict[str, Any], facts: dict[str, Any]) -> bool:
    """A bot whose demo is a live channel/server is already running with its own keys."""
    ptype = answers.get("project_type", {})
    host = _host(facts.get("demo_url") or "")
    return ptype.get("choice") == "bot" and bool(host) and bool(BOT_HOSTS.search(host))


def code_rules(answers: dict[str, Any], facts: dict[str, Any]) -> list[str]:
    """v2 checks decided by code (plus the vision banner label); no thresholds."""
    reasons: list[str] = []
    ptype = answers.get("project_type", {})
    kind = ptype.get("choice") if ptype.get("confidence", 0) >= 0.5 else None
    demo = facts.get("demo_url") or ""
    host = _host(demo)
    if facts.get("banner_is_default"):
        reasons.append("banner_default")
    elif facts.get("banner_label") in BAD_BANNERS:
        reasons.append("banner_bad")
    if host and VIDEO_HOSTS.search(host) and kind != "hardware":
        reasons.append("demo_is_video")
    if facts["demo_url_is_repo_url"] and kind not in (None, "hardware"):
        reasons.append("demo_is_repo")
    assets = facts.get("release_assets")
    if kind in BUILD_EXT and host == "github.com" and assets is not None:
        # CLI: any release asset counts; desktop/Android need a matching installable format.
        ok = bool(assets) if kind == "cli_tool" else any(
            a.lower().endswith(BUILD_EXT[kind]) for a in assets
        )
        if not ok:
            reasons.append("missing_build")
    if host.endswith("itch.io") and facts.get("demo_http_status") == 200 and facts.get("demo_text") \
            and not ITCH_PLAYABLE.search(facts.get("demo_render_all") or facts["demo_text"]):
        reasons.append("itch_no_build")
    if kind == "bot" and host and not BOT_HOSTS.search(host):
        reasons.append("bot_link_invalid")
    # No source only when GitHub reports no language bytes at all (not just unknown extensions).
    if kind not in (None, "hardware") and facts.get("tree_code_files_v2") == 0 \
            and facts.get("languages_present") and facts.get("language_bytes", 0) == 0:
        reasons.append("no_source")
    if re.match(r"\s*(untitled|new project|my project)\b", facts.get("project_name") or "", re.I):
        reasons.append("untitled")
    return reasons


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
    if facts.get("v2"):
        reasons += code_rules(answers, facts)
    for key in JEV_REASONS:
        t = thresholds.get(key)
        if t is None:
            continue
        if key == "demo_broken" and (
            not facts["demo_rendered"] or facts.get("demo_challenge")
            or facts.get("demo_engine_loading")
        ):
            continue
        if key == "needs_api_key" and _hosted_bot(answers, facts):
            continue
        if key == "feedback_ignored" and not facts["previously_rejected"]:
            continue
        if key in answers and answers[key]["noul"] >= t:
            reasons.append(key)
    return ("REJECT" if reasons else "PASS"), reasons
