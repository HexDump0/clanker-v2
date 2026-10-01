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
from typing import Any

AGENT_STATE_CHARS = 70_000  # ~20-23k tokens; Jev allows 32k for state + longest question

# The packet parser and code facts are the production ones (single source of truth).
from clanker.review.first_layer.facts import (  # noqa: E402
    BAD_DEMO_PATTERNS,  # noqa: F401  (re-exported for older eval scripts)
    CUTOFF,  # noqa: F401
    LIMITS,
    PRIVATE_FACTS,
    SECTION_KEYS,  # noqa: F401
    code_facts,
    parse_packet,
)
from clanker.review.first_layer.ai_css import modern_ai_css_signals  # noqa: E402
from clanker.review.first_layer.facts import cut as _cut  # noqa: E402


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
    ev2: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prompt = trace["messages"][0]["parts"][0]["content"]
    sec = parse_packet(prompt)
    facts = code_facts(sec)
    packet = {k: _cut(v, LIMITS.get(k, 6_000)) for k, v in sec.items() if k != "other"}
    packet_state = {
        **packet,
        "computed_facts": {
            k: v for k, v in facts.items() if k not in ("demo_text", "demo_render_all")
        },
    }

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
    if ev2 is not None:
        # v2: richer code excerpts + code/vision facts (banner label, release assets, source).
        facts.update(
            v2=True,
            banner_label=ev2.get("banner"),
            release_assets=ev2.get("release_assets"),
            tree_code_files_v2=ev2.get("tree_code_files"),
            modern_ai_css_signals=modern_ai_css_signals(
                "\n".join(
                    f["excerpt"]
                    for f in ev2.get("files") or []
                    if f["path"].lower().endswith((".css", ".scss"))
                )
            ),
        )
        states["reject2"] = {
            **packet_state,
            "computed_facts": {k: v for k, v in facts.items() if k not in PRIVATE_FACTS},
            "code_excerpts": ev2.get("files") or [],
        }
    return states
