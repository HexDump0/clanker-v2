"""Turn a frozen production trace into Jev `state` objects plus code-computed facts.

Two arms:

- ``packet``: only the deterministic pre-fetched packet (what code alone can gather).
- ``agent``: the packet plus the review agent's own tool calls/results, i.e. "the LLM
  investigates, Jev decides". DeepSeek's thinking and final answer are never included.

Jev is weak at dates, counting, and numbers, so those facts are computed here in code and
handed over as plain booleans/labels.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

CUTOFF = date(2026, 6, 1)
AGENT_STATE_CHARS = 70_000  # ~20-23k tokens; Jev allows 32k for state + longest question

# Order matters: the first matching prefix wins, so "Submission attempts" precedes "Submission".
SECTION_KEYS = {
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


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + f"\n...[truncated {len(text) - limit} chars]"


def parse_packet(prompt: str) -> dict[str, str]:
    # Split only on the packet's own section headers: README/devlog content has its own
    # "## " headings, which must stay inside their section.
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


def _field(submission: str, name: str) -> str:
    m = re.search(rf"^- {re.escape(name)}: (.*)$", submission, re.MULTILINE)
    return m.group(1).strip() if m else ""


def code_facts(sec: dict[str, str]) -> dict[str, Any]:
    sub = sec.get("submission", "")
    repo_url = _field(sub, "Repo URL")
    demo_url = _field(sub, "Demo URL")
    readme_url = _field(sub, "Readme URL")
    commits = re.findall(r"^- [0-9a-f]{6,12} (\d{4}-\d{2}-\d{2})", sec.get("github_commits", ""), re.M)
    dates = sorted(date.fromisoformat(d) for d in commits)
    created = re.search(r"created (\d{4}-\d{2}-\d{2})", sec.get("github_commits", ""))
    history = sec.get("attempt_history", "")
    render = sec.get("demo_render", "")
    status = re.search(r"\(HTTP (\d{3})\)", render)
    tree = sec.get("repo_structure", "")
    tree_files = re.findall(r"^  - (.+)$", tree, re.M)
    code_exts = (".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".kt", ".swift", ".c", ".cpp",
                 ".h", ".cs", ".rs", ".go", ".rb", ".php", ".html", ".css", ".vue", ".svelte",
                 ".dart", ".lua", ".gd", ".ino", ".sh", ".scala", ".zig", ".m", ".sql")
    bad = [name for name, pat in BAD_DEMO_PATTERNS.items() if demo_url and re.search(pat, demo_url, re.I)]
    rejections = sorted(
        date.fromisoformat(d)
        for d in re.findall(r"^  - (\d{4}-\d{2}-\d{2}) REJECTED", history, re.M)
    )
    last_rejection = rejections[-1] if rejections else None
    return {
        "previously_rejected": bool(rejections),
        "commits_after_last_rejection": (
            sum(d >= last_rejection for d in dates) if last_rejection else None
        ),
        "readme_url_is_raw_github": bool(re.match(r"https://raw\.githubusercontent\.com/", readme_url)),
        "repo_url_is_repo_root": bool(
            re.fullmatch(r"https://github\.com/[^/\s]+/[^/\s]+?(\.git)?/?", repo_url)
        ),
        "demo_url_present": bool(demo_url and demo_url != "(none)"),
        "demo_url_is_repo_url": bool(demo_url and repo_url and demo_url.rstrip("/") == repo_url.rstrip("/")),
        "demo_url_rejected_platforms": bad,
        "readme_present": "```markdown" in sec.get("readme", ""),
        "readme_chars": len(sec.get("readme", "")),
        "commit_count_in_packet": len(dates),
        "commits_before_cutoff": sum(d < CUTOFF for d in dates),
        "repo_created_before_cutoff": bool(created and date.fromisoformat(created.group(1)) < CUTOFF),
        "declared_as_updated_project": "(not declared as update)" not in _field(sub, "Updated project"),
        "distinct_commit_days": len(set(dates)),
        "prior_rejections": history.count("REJECTED by") + history.count(" REJECTED:"),
        "tree_file_count": len(tree_files),
        "tree_code_file_count": sum(f.lower().endswith(code_exts) for f in tree_files),
        "demo_http_status": int(status.group(1)) if status else None,
        "demo_viewport_mostly_empty": "Viewport was mostly empty" in render,
        "demo_rendered": bool(render),
    }


def _investigation(messages: list[dict]) -> list[dict[str, Any]]:
    calls: dict[str, dict[str, Any]] = {}
    out: list[dict[str, Any]] = []
    for msg in messages[1:]:
        for part in msg.get("parts", []):
            if part.get("type") == "tool_call":
                calls[part.get("id")] = {"tool": part.get("name"), "args": part.get("arguments")}
            elif part.get("type") == "tool_call_response":
                call = calls.get(part.get("id"), {"tool": part.get("name"), "args": None})
                result = part.get("result")
                if not isinstance(result, str):
                    result = json.dumps(result, ensure_ascii=False)
                out.append({**call, "result": result})
    return out


def _fit(steps: list[dict[str, Any]], budget: int) -> list[dict[str, Any]]:
    """Truncate tool results so the investigation fits the remaining state budget."""
    out = []
    per_result = max(1_500, budget // max(1, len(steps))) if steps else 0
    for step in steps:
        item = {**step, "result": _cut(str(step.get("result", "")), per_result)}
        size = len(json.dumps(item, ensure_ascii=False))
        if size > budget:
            break
        out.append(item)
        budget -= size
    return out


def build_states(
    trace: dict[str, Any],
    bunny: dict[str, Any] | None = None,
    code: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prompt = trace["messages"][0]["parts"][0]["content"]
    sec = parse_packet(prompt)
    facts = code_facts(sec)
    packet = {k: _cut(v, LIMITS.get(k, 6_000)) for k, v in sec.items() if k != "other"}
    packet_state = {**packet, "computed_facts": facts}

    base = len(json.dumps(packet_state, ensure_ascii=False))
    steps = _investigation(trace["messages"])
    states: dict[str, Any] = {"packet": packet_state, "facts": facts}
    # DeepSeek's production tool results (optional arm; its thinking/verdict excluded).
    states["agent"] = {
        **packet_state,
        "reviewer_investigation": _fit(steps, AGENT_STATE_CHARS - base),
    }
    if bunny and "error" not in bunny:
        notes = _cut(bunny.get("findings") or "", 4_000)
        states["bunny"] = {
            **packet_state,
            "investigator_findings": notes,
            "reviewer_investigation": _fit(bunny.get("steps") or [], AGENT_STATE_CHARS - base - len(notes)),
        }
    # First-layer "confident reject" state: packet + pinned code excerpts, no LLM involved.
    states["reject"] = {
        **packet_state,
        "code_excerpts": (code or {}).get("files") or [],
    }
    return states
