"""Data for the first-layer PDF report (``templates/first_layer_report.typ``).

The older report shows the agent's 13-check rubric, most of which the first layer never
evaluates (11 rows of "skip"). This one shows what the first layer actually knows: each
reject reason with the evidence that triggered it, the message for the shipper, every Jev
score against its limit, and the code checks that ran.
"""

from __future__ import annotations

from typing import Any

from clanker.forges import parse_repo
from clanker.review.first_layer.ai_css import REJECT_AT as AI_CSS_REJECT_AT
from clanker.review.first_layer.ai_css import SIGNALS as AI_CSS_SIGNALS
from clanker.review.first_layer.reviewer import REASON_LABELS, FirstLayerResult
from clanker.review.first_layer.rules import BUILD_EXT, JEV_REASONS, REASONS
from clanker.review.packet import ReviewPacket

AI_CSS_TOTAL = len(AI_CSS_SIGNALS) + 1  # + the named-token palette
JEV_LABELS = {
    "ai_code": "Code/CSS mostly AI-generated",
    "ai_readme": "README written with AI",
    "readme_thin": "README too thin",
    "ai_undeclared": "AI used but not declared",
    "demo_broken": "Demo fails to load",
    "needs_api_key": "Needs the reviewer's own API key",
    "demo_not_testable": "Demo can't be tried",
    "feedback_ignored": "Previous feedback not addressed",
    "not_eligible": "Not eligible",
}


def _reason_evidence(reason: str, result: FirstLayerResult) -> list[str]:
    """What triggered one reason, in plain words (shown under it in the report)."""
    facts, answers = result.facts, result.answers
    out: list[str] = []
    limit = result.thresholds.get(reason)
    if limit is not None and reason in answers and answers[reason]["noul"] >= limit:
        out.append(f"Jev score {answers[reason]['noul']:.2f} (rejects at {limit:g})")
    signals = facts.get("modern_ai_css_signals") or []
    if reason == "ai_code" and len(signals) >= AI_CSS_REJECT_AT:
        out.append(
            f"Code rule: {len(signals)}/{AI_CSS_TOTAL} modern AI CSS signals "
            f"(rejects at {AI_CSS_REJECT_AT}): {', '.join(signals)}"
        )
    if reason in ("ai_code", "ai_undeclared") and result.video_inputs.flagged_code:
        out.append("Files read: " + ", ".join(result.video_inputs.flagged_code))
    demo = facts.get("demo_url") or "(none)"
    by_code = {
        "readme_not_raw": f"README link: {result.video_inputs.ctx.readme_url or '(none)'}",
        "no_readme": "No README found in the repo",
        "bad_hosting": "Demo host: " + ", ".join(facts.get("demo_url_rejected_platforms") or []),
        "demo_is_video": f"Demo link: {demo}",
        "demo_is_repo": f"Demo link is the repo: {demo}",
        "bot_link_invalid": f"Demo link: {demo}",
        "itch_no_build": f"itch.io page has no download or browser build: {demo}",
        "missing_build": "Release assets: "
        + (", ".join(facts.get("release_assets") or []) or "none"),
        "banner_default": "The project still has the default banner",
        "banner_bad": f"Banner looks like: {(facts.get('banner_label') or '?').replace('_', ' ')}",
        "no_source": "No code files and no language bytes in the repo",
        "untitled": f"Project name: {facts.get('project_name') or '(empty)'}",
        "readme_not_english": f"README prose looks {facts.get('readme_not_english') or '?'}, "
        "with no English version linked",
        "pre_event_undeclared": _history_text(facts) + "; not declared as an updated project",
    }
    if reason in by_code:
        out.append(by_code[reason])
    if reason == "demo_broken" and facts.get("demo_http_status"):
        out.append(f"Demo returned HTTP {facts['demo_http_status']}")
    return out


def _history_text(facts: dict[str, Any]) -> str:
    h = facts.get("commit_history") or {}
    pre = h.get("pre_cutoff_own_commits", 0)
    count = f"{pre}+" if pre >= 100 else str(pre)
    text = f"{count} of {h.get('total_commits', '?')} commits before June 1"
    if pre and h.get("oldest_own_commit"):
        text += f" (oldest {h['oldest_own_commit']})"
    return text


def _jev_rows(result: FirstLayerResult) -> list[dict[str, Any]]:
    rows = []
    for key in JEV_REASONS:
        if key not in result.answers:
            continue
        score = float(result.answers[key]["noul"])
        limit = result.thresholds.get(key)
        if key in result.reasons and limit is not None and score >= limit:
            status = "fail"
        elif limit is None:
            status = "info"
        elif score >= limit - 0.2:
            status = "warn"
        else:
            status = "pass"
        rows.append(
            {
                "name": JEV_LABELS.get(key, key),
                "score": round(score, 2),
                "score_text": f"{score:.2f}",
                "limit": limit,
                "status": status,
            }
        )
    # Questions that can reject first; context-only ones (no limit) after.
    return sorted(rows, key=lambda row: row["limit"] is None)


def _code_checks(result: FirstLayerResult, packet: ReviewPacket) -> list[dict[str, str]]:
    facts = result.facts
    rows: list[dict[str, str]] = []

    def row(name: str, status: str, details: str) -> None:
        rows.append({"name": name, "status": status, "details": details})

    if facts.get("readme_present"):
        repo = parse_repo(packet.readme_source)
        source = repo.host if repo else "the Dashboard cache"
        row("README", "pass", f"{facts.get('readme_chars', 0):,} chars, from {source}")
    elif facts.get("readme_unverified"):
        row("README", "info", "Couldn't reach the repo host; not checked")
    else:
        row("README", "fail", "No README found")
    if facts.get("readme_present"):
        raw = facts.get("readme_url_is_raw")
        row("README link is raw", "pass" if raw else "fail", packet.cert.readme_url or "(none)")
    if facts.get("readme_present"):
        lang = facts.get("readme_not_english")
        row("README language", "fail" if lang else "pass", f"Looks {lang}" if lang else "English")
    if facts.get("commit_history"):
        pre = "pre_event_undeclared" in result.reasons
        declared = "declared as an update" if facts.get("declared_as_updated_project") else (
            "not declared as an update"
        )
        row("Project history", "fail" if pre else "info", f"{_history_text(facts)}; {declared}")
    bad = facts.get("demo_url_rejected_platforms") or []
    if facts.get("demo_url"):
        row(
            "Demo host",
            "fail" if bad else "pass",
            f"Disallowed: {', '.join(bad)}" if bad else "Not on a disallowed host",
        )
    else:
        row("Demo host", "info", "No demo link")
    status = facts.get("demo_http_status")
    if facts.get("demo_challenge"):
        row("Demo render", "info", "Bot wall / challenge page; not judged")
    elif facts.get("demo_rendered"):
        row("Demo render", "pass" if status and status < 400 else "warn", f"HTTP {status or '?'}")
    else:
        row("Demo render", "info", "Not rendered")
    label = facts.get("banner_label")
    if facts.get("banner_is_default"):
        row("Banner", "fail", "Default banner")
    elif label:
        bad_banner = "banner_bad" in result.reasons
        row("Banner", "fail" if bad_banner else "pass", label.replace("_", " "))
    assets = facts.get("release_assets")
    kind = (result.answers.get("project_type") or {}).get("choice")
    # Only relevant where a downloadable build is expected (or the repo has one anyway).
    if assets is not None and (kind in BUILD_EXT or assets or "missing_build" in result.reasons):
        row(
            "Release assets",
            "fail" if "missing_build" in result.reasons else "info",
            ", ".join(assets[:6]) + (" …" if len(assets) > 6 else "") if assets else "None",
        )
    files = list(result.video_inputs.flagged_code)
    count = facts.get("tree_code_files_v2")
    if count is not None or files:
        row(
            "Code sampled",
            "fail" if "no_source" in result.reasons else "info",
            f"{'?' if count is None else count} code files; read {', '.join(files) or 'none'}",
        )
    signals = facts.get("modern_ai_css_signals") or []
    if files and any(f.lower().endswith((".css", ".scss")) for f in files):
        n = len(signals)
        row(
            "Modern AI CSS style",
            "fail" if n >= AI_CSS_REJECT_AT else "warn" if n >= AI_CSS_REJECT_AT - 2 else "pass",
            f"{n}/{AI_CSS_TOTAL} signals (rejects at {AI_CSS_REJECT_AT})"
            + (f": {', '.join(signals)}" if signals else ""),
        )
    if facts.get("prior_rejections"):
        row("Previous rejections", "info", str(facts["prior_rejections"]))
    return rows


def build_report_data(result: FirstLayerResult, packet: ReviewPacket) -> dict[str, Any]:
    """Everything the first-layer template shows, as plain JSON-able data."""
    return {
        "verdict": "REJECT" if result.verdict == "REJECT" else "NEEDS HUMAN",
        "project_type": result.project_type,
        "reasons": [
            {
                "label": REASON_LABELS.get(r, r),
                "fix": REASONS.get(r, ""),
                "evidence": _reason_evidence(r, result),
            }
            for r in result.reasons
        ],
        "message": result.message or "",
        "near_misses": result.near_misses,
        "jev": _jev_rows(result),
        "code_checks": _code_checks(result, packet),
    }
