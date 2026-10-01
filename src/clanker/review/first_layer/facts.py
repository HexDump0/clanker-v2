"""Parse the review packet and compute the facts Jev must not be trusted with.

Jev is weak at dates, counting, numbers and URL shapes, so those are computed here in code
and handed to it (and to the code rules) as plain booleans/labels. The packet is parsed from
``ReviewPacket.to_prompt()`` so production sees exactly the same sections the evaluation did
(see ``AI/notes/jev-eval-results-2026-09-30.md``).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from clanker.forges import is_raw_file_url, parse_repo
from clanker.review.first_layer.ai_css import modern_ai_css_signals
from clanker.review.first_layer.language import readme_not_english

CUTOFF = date(2026, 6, 1)

# Order matters: the first matching prefix wins, so "Submission attempts" precedes "Submission".
SECTION_KEYS: dict[str, str | None] = {
    "Submission attempts": "attempt_history",
    "Submission": "submission",
    "PRIVATE reviewer context": "private_reviewer_note",
    "Prior reviews": "attempt_history",
    "Active Dashboard events": "events",
    "GitHub (cached": "github_commits",
    "Repo structure": "repo_structure",
    "Stardance ship page": "stardance_page",
    "Demo page render": "demo_render",
    "README": "readme",
    "Reviewer feedback templates": None,  # wording reference only, never evidence
}

LIMITS = {
    "readme": 15_000,
    "repo_structure": 8_000,
    "stardance_page": 8_000,
    "demo_render": 7_000,
    "github_commits": 4_000,
    "attempt_history": 4_000,
}

BAD_DEMO_PATTERNS = {
    "google_drive": r"drive\.google\.com|docs\.google\.com",
    "colab": r"colab\.research\.google\.com",
    "kaggle": r"kaggle\.com",
    "huggingface": r"huggingface\.co|hf\.space",
    "render_free": r"\.onrender\.com",
    "railway": r"\.up\.railway\.app",
    "streamlit": r"\.streamlit\.app|share\.streamlit\.io",
    "tunnel": r"ngrok|trycloudflare|cloudflared|duckdns|loca\.lt|serveo",
    "localhost": r"localhost|127\.0\.0\.1",
    "source_zip": r"\.zip(\?|$)",
    "raw_source_file": r"\.(py|js|ts|java|cpp|c|rs|go)(\?|$)",
}

CODE_EXTS = (
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".kt", ".swift", ".c", ".cpp", ".h", ".cs",
    ".rs", ".go", ".rb", ".php", ".html", ".css", ".vue", ".svelte", ".dart", ".lua", ".gd",
    ".ino", ".sh", ".scala", ".zig", ".m", ".sql",
)  # fmt: skip

# Long raw texts used by code rules but never shown to Jev.
# Kept out of Jev's state so the code CSS rule doesn't silently change Jev's answers.
PRIVATE_FACTS = (
    "demo_text",
    "demo_render_all",
    "modern_ai_css_signals",
    "readme_not_english",
    "commit_history",
)


def cut(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated {len(text) - limit} chars]"


def parse_packet(prompt: str) -> dict[str, str]:
    """Split the packet prompt into its sections.

    Only the packet's own section headers split: README/devlog content has its own "## "
    headings, which must stay inside their section.
    """
    sections: dict[str, str] = {}
    key: str | None = "other"
    buf: list[str] = []

    def flush() -> None:
        if key is not None and buf:
            body = "\n".join(buf).strip()
            sections[key] = (sections[key] + "\n" + body) if key in sections else body

    for line in prompt.split("\n"):
        if line.startswith("## "):
            title = line[3:]
            match = next((v for k, v in SECTION_KEYS.items() if title.startswith(k)), "")
            if match != "":
                flush()
                key, buf = match, []
                continue
        buf.append(line)
    flush()
    return sections


def field(text: str, name: str) -> str:
    m = re.search(rf"^- {re.escape(name)}: (.*)$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def code_facts(sec: dict[str, str]) -> dict[str, Any]:
    sub = sec.get("submission", "")
    repo_url = field(sub, "Repo URL")
    demo_url = field(sub, "Demo URL")
    readme_url = field(sub, "Readme URL")
    github = sec.get("github_commits", "")
    commits = re.findall(r"^- [0-9a-f]{6,12} (\d{4}-\d{2}-\d{2})", github, re.M)
    dates = sorted(date.fromisoformat(d) for d in commits)
    created = re.search(r"created (\d{4}-\d{2}-\d{2})", github)
    history = sec.get("attempt_history", "")
    render = sec.get("demo_render", "")
    status = re.search(r"\(HTTP (\d{3})\)", render)
    tree = sec.get("repo_structure", "")
    tree_files = re.findall(r"^  - (.+)$", tree, re.M)
    bad = [
        name
        for name, pattern in BAD_DEMO_PATTERNS.items()
        if demo_url and re.search(pattern, demo_url, re.I)
    ]
    rejections = sorted(
        date.fromisoformat(d)
        for d in re.findall(r"^  - (\d{4}-\d{2}-\d{2}) REJECTED", history, re.M)
    )
    last_rejection = rejections[-1] if rejections else None
    demo_text = (
        render.split("Rendered visible text:", 1)[1] if "Rendered visible text:" in render else ""
    )
    return {
        "project_name": field(sub, "Project name"),
        "demo_url": demo_url if demo_url != "(none)" else "",
        "demo_text": demo_text.strip()[:3000],
        "banner_is_default": bool(
            re.search(r"^- banner_is_default: True", sec.get("stardance_page", ""), re.M)
        ),
        "previously_rejected": bool(rejections),
        "commits_after_last_rejection": (
            sum(d >= last_rejection for d in dates) if last_rejection else None
        ),
        "readme_url_is_raw_github": bool(
            re.match(r"https://raw\.githubusercontent\.com/", readme_url)
        ),
        # Any forge's raw file link (GitHub, GitLab, Codeberg/Gitea, Bitbucket, sourcehut).
        "readme_url_is_raw": is_raw_file_url(readme_url),
        "repo_host": repo.kind if (repo := parse_repo(repo_url)) else "unknown",
        "repo_url_is_repo_root": bool(
            repo
            and repo_url.rstrip("/").removesuffix(".git").lower() == repo.web_url.lower()
        ),
        "demo_url_present": bool(demo_url and demo_url != "(none)"),
        "demo_url_is_repo_url": bool(
            demo_url and repo_url and demo_url.rstrip("/") == repo_url.rstrip("/")
        ),
        "demo_url_rejected_platforms": bad,
        "readme_present": "```markdown" in sec.get("readme", ""),
        # Language the README prose is in when it isn't English (and no English version
        # is linked); None when English or unclear.
        "readme_not_english": _readme_language_issue(sec.get("readme", "")),
        # Non-GitHub host unreachable: a missing README is unknown, not proven.
        "readme_unverified": "not verified)" in sec.get("readme", ""),
        "readme_chars": len(sec.get("readme", "")),
        "commit_count_in_packet": len(dates),
        "commits_before_cutoff": sum(d < CUTOFF for d in dates),
        "repo_created_before_cutoff": bool(
            created and date.fromisoformat(created.group(1)) < CUTOFF
        ),
        "declared_as_updated_project": "(not declared as update)"
        not in field(sub, "Updated project"),
        "distinct_commit_days": len(set(dates)),
        "prior_rejections": history.count("REJECTED by") + history.count(" REJECTED:"),
        "tree_file_count": len(tree_files),
        "tree_code_file_count": sum(f.lower().endswith(CODE_EXTS) for f in tree_files),
        "demo_http_status": int(status.group(1)) if status else None,
        "demo_viewport_mostly_empty": "Viewport was mostly empty" in render,
        "demo_rendered": bool(render),
        # A bot wall (Cloudflare etc.) or a game engine still loading is not a broken demo.
        "demo_challenge": bool(
            re.search(
                r"cloudflare|verify (you are|you're) human|security verification|just a moment|"
                r"captcha|\(HTTP (403|429)\)",
                render,
                re.I,
            )
        ),
        "demo_engine_loading": bool(
            "Viewport was mostly empty" in render
            and re.search(r"unity|godot|webgl|loading|splash", render, re.I)
        ),
        "demo_render_all": render[:6000],
        # GitHub language byte counts: real source shows up here even when the files use
        # extensions the list above doesn't know (.pyw, .luau, ...).
        "languages_present": "- Languages:" in tree,
        "language_bytes": sum(
            int(n) for n in re.findall(r"\((\d+) bytes\)", tree.split("- File tree", 1)[0])
        ),
    }


def _readme_language_issue(section: str) -> str | None:
    m = re.search(r"```markdown\n(.*)```", section, re.S)
    guess = readme_not_english(m.group(1)) if m else None
    return guess.language if guess else None


def packet_state(sec: dict[str, str], facts: dict[str, Any]) -> dict[str, Any]:
    """Packet sections (bounded) plus the public computed facts, as Jev's `state`."""
    return {
        **{k: cut(v, LIMITS.get(k, 6_000)) for k, v in sec.items() if k != "other"},
        "computed_facts": {k: v for k, v in facts.items() if k not in PRIVATE_FACTS},
    }


def add_evidence(facts: dict[str, Any], evidence: dict[str, Any]) -> None:
    """Merge the extra gathered evidence (banner label, release assets, source count)."""
    facts.update(
        v2=True,
        banner_label=evidence.get("banner"),
        release_assets=evidence.get("release_assets"),
        tree_code_files_v2=evidence.get("tree_code_files"),
        # Commit counts around the cutoff from the forge API (GitHub/GitLab), or None.
        commit_history=evidence.get("history"),
        modern_ai_css_signals=modern_ai_css_signals(
            "\n".join(
                f["excerpt"]
                for f in evidence.get("files") or []
                if f["path"].lower().endswith((".css", ".scss"))
            )
        ),
    )


def build_jev_state(
    prompt: str, evidence: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    """(state for Jev, facts for the rules, parsed sections) for one review."""
    sec = parse_packet(prompt)
    facts = code_facts(sec)
    add_evidence(facts, evidence)
    state = {**packet_state(sec, facts), "code_excerpts": evidence.get("files") or []}
    if not sec.get("repo_structure") and evidence.get("tree_paths"):
        # Non-GitHub repos have no packet tree; give Jev the forge's file list instead.
        listing = "\n".join(f"  - {path}" for path in evidence["tree_paths"])
        state["repo_structure"] = cut(
            f"Files (from the repo host):\n{listing}", LIMITS["repo_structure"]
        )
    return state, facts, sec
