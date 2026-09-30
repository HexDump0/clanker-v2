"""Render a no-LLM rejection video for one real first-layer reject.

    JEV_DATASET=holdout uv run --with typesafe-sdk==0.7.2 python evals/jev/demo_video.py <cert-id-prefix>
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from pathlib import Path

from common import DATA, RESULTS, TRACES, read_jsonl
from questions_reject import reject_decision
from state import build_states, parse_packet

from clanker.review.reject_message import RejectContext, compose_reject_message
from clanker.review.video.compositor import DEFAULT_MUSIC
from clanker.review.video.pipeline import generate_reject_video
from clanker.review.video.template_director import RejectVideoInputs

V2 = json.loads((Path(__file__).parent / "thresholds_conservative2.json").read_text())


async def main(prefix: str) -> None:
    trace = next(t for t in read_jsonl(TRACES) if t["cert_id"].startswith(prefix))
    result = next(r for r in read_jsonl(RESULTS)
                  if r["trace_id"] == trace["trace_id"] and r.get("arm") == "reject2")
    ev2 = next(e for e in read_jsonl(DATA / "evidence2.jsonl") if e["trace_id"] == trace["trace_id"])
    prompt = trace["messages"][0]["parts"][0]["content"]
    facts = build_states(trace, ev2=ev2)["facts"]
    verdict, reasons = reject_decision(result["answers"], facts, V2)
    assert verdict == "REJECT", f"{prefix} is not a reject"

    def field(k: str) -> str | None:
        m = re.search(rf"^- {k}: (.*)$", prompt, re.M)
        return m.group(1).strip() if m else None

    ctx = RejectContext(
        submitter=field("Submitter"), repo_url=field("Repo URL"), readme_url=field("Readme URL"),
        demo_url=field("Demo URL"), project_type=result["answers"]["project_type"]["choice"],
        banner_label=facts.get("banner_label"), bad_hosts=facts["demo_url_rejected_platforms"],
        ai_style_file=any(f["path"].endswith((".css", ".scss")) for f in ev2.get("files") or []),
    )
    readme = parse_packet(prompt).get("readme", "")
    readme = readme.split("```markdown", 1)[-1].rsplit("```", 1)[0]
    sha = re.search(r"^- ([0-9a-f]{7,40}) \d{4}-\d{2}-\d{2}T", prompt, re.M)
    inputs = RejectVideoInputs(
        ctx=ctx, repo_url=ctx.repo_url, commit=sha.group(1) if sha else None,
        banner_url=field("banner_url"), readme_markdown=readme,
        flagged_code={f["path"]: f["excerpt"] for f in ev2.get("files") or []},
        project_name=facts["project_name"],
    )
    seed = trace["cert_id"]
    print("reasons:", reasons)
    print("message:\n" + compose_reject_message(reasons, ctx, seed) + "\n")

    out_dir = Path("data/videos/demo") / prefix
    started = time.perf_counter()
    result = await generate_reject_video(
        reasons=reasons, inputs=inputs, seed=seed, work_dir=out_dir,
        output_path=out_dir / "reject.mp4", music_path=DEFAULT_MUSIC,
    )
    manifest = json.loads(result.manifest_path.read_text())
    for scene in manifest["scenes"]:
        print(f"scene {scene['directed']['evidence_id']}: highlight={scene['resolution']}")
    stages = [a["stage"] for a in manifest["audit"]]
    print(f"\nvideo: {result.video.path} ({result.video.duration_seconds:.1f}s, "
          f"{result.video.size_bytes // 1024} KB) · stages: {stages}")
    print(f"total {time.perf_counter() - started:.1f}s · model calls: 0 · "
          f"capture failures: {result.capture_failures}")

if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
