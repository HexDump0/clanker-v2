"""Compose first-layer rejection messages that read like a Shipwright wrote them.

No model writes these. Each reject reason has several short phrasings modeled on real
Shipwright review comments (casual tone, "reship", "#ask-the-shipwrights"); code picks and
assembles them. Choices are seeded by the cert id, so the same submission always gets the
same message, and different submissions get varied wording.

House rules, taken from how reviewers actually write:
- a greeting, a light generic compliment, then the issue(s); one or two issues inline,
  three or more as "- " bullets;
- never claim someone tried, clicked, or tested something ("when I tried..."): state facts;
- never sign as a specific person; point to #ask-the-shipwrights instead;
- no em dashes, no "Additionally"/"Furthermore"/"I hope this helps", no emoji headers.
"""

from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass, field

# Reviewers rarely list more than three problems; the most blocking ones come first (ORDER).
MAX_ISSUES = 3
GREAT_README = "https://stardance.hackclub.com/resources/great_readme"
HOW_TO_SHIP = "https://stardance.hackclub.com/resources/how_to_ship"


@dataclass(slots=True)
class RejectContext:
    """Facts the message may mention. Everything is optional."""

    submitter: str | None = None
    repo_url: str | None = None
    readme_url: str | None = None
    demo_url: str | None = None
    project_type: str | None = None
    banner_label: str | None = None
    bad_hosts: list[str] = field(default_factory=list)
    ai_style_file: bool = False  # the flagged code includes a stylesheet


GREETINGS = ["Hey there!", "Hi there!", "Hello!", "Hey!", "Hi!"]
NAMED_GREETINGS = ["Hey {name}!", "Hi {name}!", "Hello {name}!"]
COMPLIMENTS = [
    "Cool project, but",
    "Nice project, but",
    "Awesome project, but",
    "I like the idea of your project a lot. However,",
    "Thanks for shipping your project! It's not quite ready yet though,",
    "Cool idea! Unfortunately",
    "Nice work, but",
    "Love the idea, but",
]
# Lead-ins that read naturally before a "please fix the following:" style list.
LIST_COMPLIMENTS = [
    "Cool project, but",
    "Nice work, but",
    "I like the idea of your project a lot. However,",
    "Thanks for shipping your project!",
]
LIST_INTROS = [
    "please fix the following so we can accept it:",
    "here's what needs to change before we can accept it:",
    "there are a few things to fix first:",
]
CLOSINGS_ONE = [
    "Once that's fixed, reship and we'll take another look!",
    "Fix it and reship!",
    "Please fix this and resubmit!",
]
CLOSINGS_MANY = [
    "Once you've made these changes, ship it again and we'll take another look!",
    "Fix these and reship!",
    "Please fix these and resubmit!",
]
QUESTIONS = [
    "If you have any questions, ask in #ask-the-shipwrights.",
    "If you have any questions, feel free to ask in #ask-the-shipwrights on Slack!",
    "For any questions, create a ticket in #ask-the-shipwrights.",
    "Any questions can go in #ask-the-shipwrights.",
]

BANNER_WHAT = {
    "code_screenshot": "a screenshot of your code",
    "logo_or_text": "a logo",
    "ai_generated_art": "AI art",
    "unrelated": "an unrelated image",
}
HOST_NAMES = {
    "render_free": "Render",
    "railway": "Railway",
    "streamlit": "Streamlit",
    "tunnel": "tunnel",
    "google_drive": "Google Drive",
    "colab": "Colab",
    "kaggle": "Kaggle",
    "huggingface": "Hugging Face",
    "localhost": "localhost",
    "source_zip": "zip file",
    "raw_source_file": "raw source file",
}
DEMO_BY_TYPE = {
    "web_app": "the live website",
    "desktop_app": "a GitHub release with the executable",
    "cli_tool": "a GitHub release with the binary, or the package page",
    "library": "the package page (npm, PyPI, crates.io, etc.)",
    "android_app": "a GitHub release with the APK or the Play Store page",
    "game": "a playable build or your itch.io page",
    "game_mod": "the mod page on Modrinth, CurseForge or similar",
    "browser_extension": "the extension's store page",
    "bot": "a server or channel where people can use the bot",
}
BUILD_BY_TYPE = {
    "desktop_app": "an actual executable (.exe, .dmg, .AppImage or similar)",
    "android_app": "the APK",
    "cli_tool": "a prebuilt binary",
}


def raw_readme_url(readme_url: str | None, repo_url: str | None) -> str | None:
    """Best-effort raw.githubusercontent.com URL for the README, or None if unsure."""
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+?)/?$", readme_url or "")
    if m:
        owner, repo, ref, path = m.groups()
        return f"https://raw.githubusercontent.com/{owner}/{repo}/refs/heads/{ref}/{path}"
    return None


def _phrases(reason: str, ctx: RejectContext) -> list[str]:
    """Human-style phrasings for one reason (lowercase start; composed later)."""
    kind = ctx.project_type or ""
    if reason == "ai_code":
        part = "the CSS" if ctx.ai_style_file else "the code"
        return [
            f"it looks like a lot of your project is AI-generated, which is over our 30% limit. "
            f"please rewrite {part} yourself and add some features you came up with",
            f"your project seems to use an excessive amount of AI. please rewrite {part} by hand "
            f"and make it something that's really yours",
            f"a lot of {part} looks and feels AI-generated (the limit is 30%). please rework it "
            f"yourself and give it your own style",
        ]
    if reason == "ai_readme_thin":
        return [
            "your README seems to be written with AI and is missing detail. Please rewrite it "
            f"yourself: what the project is, its features, how to use it and how you made it "
            f"({GREAT_README})",
            "the README looks AI-written and too thin. Please rewrite it in your own words and "
            "add more about how the project works and how you built it",
        ]
    if reason == "ai_readme":
        return [
            "your README seems to be written with AI. please rewrite it yourself, we'd like to "
            "see how you worked on the project",
            "the README looks AI-written, please rewrite it in your own words",
            "it looks like you used a lot of AI in your README. please rewrite it yourself and "
            "talk about how you made the project",
        ]
    if reason == "readme_thin":
        return [
            f"your README needs more detail. Add what the project does, its features, how to use "
            f"it and how you made it ({GREAT_README})",
            "your README is too minimal right now, please expand it with more info about the "
            "project, how to use it and some screenshots",
            f"please add more information to your README (this guide helps: {GREAT_README})",
        ]
    if reason == "readme_not_raw":
        raw = raw_readme_url(ctx.readme_url, ctx.repo_url)
        if raw:
            return [
                f"your README link isn't raw, please set it to {raw} before reshipping",
                f"the README link needs to be the raw file. please set it to {raw}",
            ]
        return [
            "your README link isn't raw. open your README on GitHub, click \"Raw\" and use that "
            "raw.githubusercontent.com link",
            "the README link needs to be the raw file (raw.githubusercontent.com), not the GitHub "
            "page",
        ]
    if reason == "no_readme":
        return ["your repo doesn't have a README yet, please add one",
                "there's no README in the repo, please add one that explains the project"]
    if reason == "ai_undeclared":
        return [
            "it seems AI was used in the project but it isn't declared. please declare it honestly "
            "in the AI declaration field",
            "please declare your AI usage honestly on the AI declaration field, no matter how "
            "minor",
        ]
    if reason == "bad_hosting":
        hosts = " / ".join(dict.fromkeys(HOST_NAMES.get(h, h) for h in ctx.bad_hosts)) or "that"
        return [
            f"we can't accept {hosts} links for the demo since they sleep or take a long time to "
            f"load. please host it on something like Vercel, Netlify or GitHub Pages",
            f"the demo can't be a {hosts} link. please use permanent hosting like Vercel, Netlify "
            f"or GitHub Pages",
        ]
    if reason == "demo_broken":
        return ["your demo link doesn't seem to load right now",
                "the demo page fails to load, so please check your deployment"]
    if reason == "demo_is_video":
        return ["your demo link needs to let people actually try the project, not a video",
                "the demo can't be a video, please link somewhere people can use the project"]
    if reason == "demo_is_repo":
        target = DEMO_BY_TYPE.get(kind, "somewhere people can try the project")
        return [f"your demo link points to your repo, please change it to {target}",
                f"the demo link should be {target} instead of the GitHub repo"]
    if reason == "missing_build":
        build = BUILD_BY_TYPE.get(kind, "a downloadable build")
        return [f"your GitHub release needs to include {build}",
                f"please upload {build} to a GitHub release and link that as the demo"]
    if reason == "itch_no_build":
        return ["your itch page should have a downloadable or playable build of the game",
                "the itch.io page needs an actual build people can download or play"]
    if reason == "bot_link_invalid":
        return ["your bot's demo link should point to a public channel or server where people "
                "can try the bot",
                "the demo for a bot should be a channel or server invite so people can use it"]
    if reason == "banner_default":
        return ["please add a banner that shows your project in action, you can set it in "
                "project settings"]
    if reason == "banner_bad":
        what = BANNER_WHAT.get(ctx.banner_label or "", "that image")
        return [
            f"your banner should be a screenshot of your project in action, not {what}. you can "
            f"change it in project settings",
            f"the banner needs to show your project in action instead of {what}",
        ]
    if reason == "no_source":
        return ["the repo seems to be missing the source code, please push it",
                "your repo doesn't have the project's source code yet, please add it"]
    if reason == "untitled":
        return ["your project seems to be named 'untitled', please give it a proper name"]
    if reason == "needs_api_key":
        return ["please include a working API key in the demo so it can be tested. Hack Club "
                "AI is a good free option",
                "the demo needs to work without people bringing their own API key. Hack Club AI "
                "is a free option you can use"]
    if reason == "feedback_ignored":
        return ["please make the changes requested in the previous review before reshipping"]
    if reason == "not_eligible":
        return [f"this project doesn't look eligible, please check {HOW_TO_SHIP}"]
    return []


# Order issues the way reviewers tend to: submission/format fixes, then AI, then README detail.
ORDER = [
    "no_source", "no_readme", "untitled", "readme_not_raw", "bad_hosting", "demo_is_repo",
    "demo_is_video", "missing_build", "itch_no_build", "bot_link_invalid", "demo_broken",
    "needs_api_key", "banner_default", "banner_bad", "ai_code", "ai_undeclared",
    "ai_readme_thin", "ai_readme", "readme_thin", "feedback_ignored", "not_eligible",
]


def _sentence_case(text: str) -> str:
    """Capitalise the first letter after a sentence end (reviewers mostly write this way)."""
    return re.sub(r"([.!?] )([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def compose_reject_message(reasons: list[str], ctx: RejectContext, seed: str) -> str:
    """Build the message for the given reject reasons. Deterministic for a given seed."""
    rng = random.Random(int(hashlib.sha256(seed.encode()).hexdigest()[:16], 16))
    wanted = set(reasons)
    if {"ai_readme", "readme_thin"} <= wanted:  # one README sentence, not two
        wanted -= {"ai_readme", "readme_thin"}
        wanted.add("ai_readme_thin")
    issues = [_sentence_case(rng.choice(p)) for r in sorted(wanted & set(ORDER), key=ORDER.index)
              if (p := _phrases(r, ctx))][:MAX_ISSUES]
    if not issues:
        raise ValueError("no known reject reasons to describe")

    name = (ctx.submitter or "").strip()
    greeting = (rng.choice(NAMED_GREETINGS).format(name=name)
                if name and rng.random() < 0.35 else rng.choice(GREETINGS))
    pool = LIST_COMPLIMENTS if len(issues) > 2 else COMPLIMENTS
    if re.match(r"(your project|it looks like a lot of your project)", issues[0], re.I):
        pool = [c for c in pool if "project" not in c]  # avoid "Nice project, but your project"
    if issues[0].lower().startswith("please"):
        pool = [c for c in pool if not c.endswith("Unfortunately")]  # not "Unfortunately please"
    compliment = rng.choice(pool)

    if len(issues) == 1:
        body = f"{compliment} {issues[0]}."
    elif len(issues) == 2:
        body = f"{compliment} {issues[0]}. Also, {issues[1]}."
    else:
        bullets = "\n".join(f"- {_cap(i)}" for i in issues)
        intro = rng.choice(LIST_INTROS)
        if compliment.endswith("!"):  # a full sentence, so the list intro starts a new one
            intro = _cap(intro)
        body = f"{compliment} {intro}\n{bullets}\n"

    closings = CLOSINGS_ONE if len(issues) == 1 else CLOSINGS_MANY
    closing = f"{rng.choice(closings)} {rng.choice(QUESTIONS)}"
    message = f"{greeting} {body}{'' if body.endswith(chr(10)) else ' '}{closing}"
    # Lowercase the first issue word after a comma-style compliment, capitalise after a period.
    message = re.sub(r"(However,|but|though,|Unfortunately) (\w)",
                     lambda m: f"{m.group(1)} {m.group(2).lower()}", message)
    return message.replace("—", ",").strip()
