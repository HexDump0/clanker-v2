#!/usr/bin/env python3
# ruff: noqa: E501
"""Capture evidence and render the hand-directed ferrocompiler benchmark video.

This is intentionally a transparent benchmark harness, not production orchestration.
Its input is the checked-in director script; its outputs are ignored runtime assets.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import html
import json
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCRIPT = ROOT / "AI/notes/video-benchmark/ferrocompiler-director-script.json"
DEFAULT_ASSETS = ROOT / "data/video-director/ferrocompiler"
DEFAULT_OUTPUT = ROOT / "data/videos/ferrocompiler-director-cut.mp4"
VIEWPORT = {"width": 1280, "height": 720}
ALLOWED_HOSTS = {"github.com"}


def _read_script(path: Path) -> dict:
    return json.loads(path.read_text())


def _validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"benchmark URL is not allowlisted: {url}")


async def _target_locator(page, target: dict):
    if target["kind"] == "selector":
        return page.locator(target["value"]).first
    return page.get_by_text(target["value"], exact=True).first


async def capture_evidence(script: dict, assets_dir: Path) -> list[dict]:
    assets_dir.mkdir(parents=True, exist_ok=True)
    captures: list[dict] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, channel="chromium")
        context = await browser.new_context(
            viewport=VIEWPORT,
            screen=VIEWPORT,
            reduced_motion="reduce",
            color_scheme="dark",
            service_workers="block",
            accept_downloads=False,
        )
        page = await context.new_page()
        page.set_default_timeout(10_000)

        for scene in script["scenes"]:
            _validate_public_url(scene["url"])
            response = await page.goto(scene["url"], wait_until="domcontentloaded", timeout=20_000)
            await page.wait_for_timeout(1_200)
            locator = await _target_locator(page, scene["target"])
            await locator.wait_for(state="visible")
            target_box = await locator.bounding_box()
            if not target_box:
                raise RuntimeError(f"target has no visible bounds: {scene['id']}")

            screenshot_path = assets_dir / f"{scene['id']}.png"
            await page.screenshot(
                path=screenshot_path,
                animations="disabled",
                caret="hide",
                scale="css",
                style="""
                    .auth-form-body.Popover { display: none !important; }
                    [data-testid='issue-pr-hovercard'] { display: none !important; }
                """,
            )
            captures.append(
                {
                    **scene,
                    "resolved_url": page.url,
                    "page_title": await page.title(),
                    "http_status": response.status if response else None,
                    "captured_at": datetime.now(UTC).isoformat(),
                    "screenshot": str(screenshot_path),
                    "target_box": target_box,
                }
            )

        await context.close()
        await browser.close()

    (assets_dir / "captures.json").write_text(json.dumps(captures, indent=2) + "\n")
    return captures


def _data_url(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def _callout_style(scene: dict) -> str:
    if scene["callout_side"] == "right":
        return "right:56px;top:246px"
    return "left:56px;top:242px"


def _evidence_scene(scene: dict, index: int, total: int) -> str:
    box = scene["target_box"]
    rect = json.dumps(
        {
            "x": max(8, box["x"] - 12),
            "y": max(8, box["y"] - 12),
            "w": min(VIEWPORT["width"] - 16, box["width"] + 24),
            "h": min(VIEWPORT["height"] - 16, box["height"] + 24),
        }
    )
    captured_date = datetime.fromisoformat(scene["captured_at"]).strftime("%d %b %Y")
    return f"""
      <section class="scene evidence" data-scene="{index}">
        <div class="browser-frame">
          <div class="capture">
            <img src="{_data_url(Path(scene["screenshot"]))}" alt="Captured evidence">
            <canvas class="evidence-canvas" width="1280" height="720"
              data-rect='{html.escape(rect)}'></canvas>
          </div>
          <div class="toolbar">
            <span class="source-label">SOURCE</span>
            <span class="address">{html.escape(scene["resolved_url"])}</span>
            <span class="capture-date">Captured {captured_date}</span>
          </div>
          <article class="callout" style="{_callout_style(scene)}">
            <div class="eyebrow">{html.escape(scene["eyebrow"])}</div>
            <h2>{html.escape(scene["title"])}</h2>
            <p>{html.escape(scene["body"])}</p>
            <div class="fix"><b>FIX</b>{html.escape(scene["fix"])}</div>
          </article>
          <div class="scene-index">{index:02d} / {total:02d}</div>
        </div>
      </section>
    """


def build_composition(script: dict, captures: list[dict]) -> tuple[str, float]:
    timing = script["timing"]
    cursor = 0.0
    timeline: list[dict] = []

    intro_end = timing["intro_seconds"] + timing["crossfade_seconds"]
    timeline.append({"selector": ".intro", "start": 0.0, "end": intro_end})
    cursor = timing["intro_seconds"]

    evidence_html = []
    for index, scene in enumerate(captures, 1):
        start = cursor
        end = start + scene["duration_seconds"] + timing["crossfade_seconds"]
        timeline.append({"selector": f'[data-scene="{index}"]', "start": start, "end": end})
        evidence_html.append(_evidence_scene(scene, index, len(captures)))
        cursor += scene["duration_seconds"]

    outro_start = cursor
    total_duration = outro_start + timing["outro_seconds"]
    timeline.append({"selector": ".outro", "start": outro_start, "end": total_duration})
    fixes = "".join(
        f"<li><span>{i:02d}</span>{html.escape(fix)}</li>"
        for i, fix in enumerate(script["required_fixes"], 1)
    )

    document = f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; width: 1280px; height: 720px; overflow: hidden; background: #0b0b0c; }}
body {{ font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; color: #f2f2f2; }}
.scene {{ position: absolute; inset: 0; opacity: 0; overflow: hidden; background: #0b0b0c; }}
.intro, .outro {{ display: grid; place-items: center; }}
.intro-inner, .outro-inner {{ width: 1010px; position: relative; }}
.kicker {{ color: #ec3750; font-size: 13px; font-weight: 750; letter-spacing: .14em; }}
.intro h1 {{ margin: 18px 0 0; max-width: 900px; font-size: 59px; line-height: 1.04; letter-spacing: -.035em; font-weight: 720; }}
.project {{ display: flex; align-items: center; gap: 14px; margin-top: 32px; padding-top: 20px; border-top: 1px solid #303034; font-size: 18px; color: #a5a5aa; }}
.project strong {{ color: #fff; }}
.verdict {{ margin-left: auto; color: #ec3750; padding-left: 12px; border-left: 2px solid #ec3750; font-weight: 800; font-size: 13px; letter-spacing: .1em; }}
.summary {{ max-width: 760px; margin-top: 17px; color: #aaaab0; font-size: 19px; line-height: 1.5; }}
.browser-frame {{ position: absolute; inset: 20px; overflow: hidden; border: 1px solid #303034; border-radius: 6px; background: #111113; }}
.capture {{ position: absolute; inset: 0; }}
.capture img, .evidence-canvas {{ position: absolute; inset: 0; width: 100%; height: 100%; }}
.capture img {{ object-fit: cover; }}
.evidence-canvas {{ z-index: 2; }}
.toolbar {{ position: absolute; z-index: 4; top: 0; left: 0; right: 0; height: 50px; display: flex; align-items: center; padding: 0 18px; border-bottom: 1px solid #303034; background: #111113; }}
.source-label {{ color: #ec3750; font-size: 10px; font-weight: 800; letter-spacing: .13em; margin-right: 14px; }}
.address {{ font-size: 14px; font-weight: 620; color: #ededee; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.capture-date {{ margin-left: auto; color: #77777d; font-size: 11px; white-space: nowrap; padding-left: 20px; }}
.callout {{ position: absolute; z-index: 5; width: 455px; padding: 23px 25px 24px; border: 1px solid #414146; border-left: 3px solid #ec3750; border-radius: 3px; background: #111113; }}
.eyebrow {{ color: #ec3750; font-size: 10px; font-weight: 800; letter-spacing: .12em; }}
.callout h2 {{ margin: 11px 0 11px; font-size: 27px; line-height: 1.14; letter-spacing: -.02em; font-weight: 700; }}
.callout p {{ margin: 0; color: #bdbdc2; font-size: 16px; line-height: 1.5; }}
.fix {{ display: flex; gap: 11px; align-items: baseline; margin-top: 18px; padding-top: 15px; border-top: 1px solid #353538; color: #ededee; font-size: 14px; line-height: 1.35; }}
.fix b {{ flex: none; color: #ec3750; font-size: 10px; letter-spacing: .14em; }}
.scene-index {{ position: absolute; z-index: 5; right: 22px; bottom: 18px; color: #88888d; font-size: 11px; font-variant-numeric: tabular-nums; letter-spacing: .12em; }}
.outro-inner {{ display: grid; grid-template-columns: .8fr 1.2fr; gap: 80px; align-items: start; }}
.outro h2 {{ margin: 14px 0 0; font-size: 48px; line-height: 1.06; letter-spacing: -.035em; font-weight: 700; }}
.outro ul {{ list-style: none; margin: 2px 0 0; padding: 0; }}
.outro li {{ display: grid; grid-template-columns: 48px 1fr; gap: 15px; padding: 20px 0; border-top: 1px solid #303034; font-size: 20px; line-height: 1.4; }}
.outro li:last-child {{ border-bottom: 1px solid #303034; }}
.outro li span {{ color: #ec3750; font-size: 13px; font-weight: 800; letter-spacing: .1em; padding-top: 7px; }}
.wordmark {{ position: absolute; left: 0; bottom: -104px; color: #66666b; font-size: 11px; font-weight: 700; letter-spacing: .13em; }}
</style></head><body>
  <section class="scene intro">
    <div class="intro-inner">
      <div class="kicker">SW-CLANKER REVIEW · REPOSITORY ACCESS</div>
      <h1>{html.escape(script["headline"])}</h1>
      <div class="project"><strong>{html.escape(script["project_name"])}</strong><span>by {html.escape(script["project_author"])}</span><span class="verdict">{html.escape(script["verdict"])}</span></div>
      <div class="summary">{html.escape(script["summary"])}</div>
    </div>
  </section>
  {"".join(evidence_html)}
  <section class="scene outro">
    <div class="outro-inner">
      <div><div class="kicker">BEFORE RESUBMITTING</div><h2>Two things<br>to fix.</h2></div>
      <ul>{fixes}</ul>
      <div class="wordmark">SW-CLANKER · EVIDENCE-BASED REVIEW</div>
    </div>
  </section>
<script>
const timeline = {json.dumps(timeline)};
const fade = {timing["crossfade_seconds"]};
const started = performance.now();
const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));

function paintEvidence(canvas) {{
  const rect = JSON.parse(canvas.dataset.rect);
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, 1280, 720);
  ctx.fillStyle = 'rgba(5, 5, 10, .68)';
  ctx.fillRect(0, 0, 1280, 720);
  ctx.clearRect(rect.x, rect.y, rect.w, rect.h);
  ctx.strokeStyle = '#ec3750';
  ctx.lineWidth = 2;
  ctx.strokeRect(rect.x + 1, rect.y + 1, rect.w - 2, rect.h - 2);
}}

function frame(now) {{
  const t = (now - started) / 1000;
  for (const item of timeline) {{
    const node = document.querySelector(item.selector);
    const fadeIn = clamp((t - item.start) / fade, 0, 1);
    const fadeOut = clamp((item.end - t) / fade, 0, 1);
    node.style.opacity = Math.min(fadeIn, fadeOut);
    if (node.classList.contains('evidence')) {{
      paintEvidence(node.querySelector('canvas'));
    }}
  }}
  requestAnimationFrame(frame);
}}
requestAnimationFrame(frame);
</script></body></html>"""
    return document, total_duration


async def render_video(document: str, duration: float, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="clanker-director-cut-") as tmp:
        webm = Path(tmp) / "director-cut.webm"
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True, channel="chromium")
            context = await browser.new_context(viewport=VIEWPORT, screen=VIEWPORT)
            page = await context.new_page()
            await page.set_content(document, wait_until="load")
            await page.screencast.start(path=webm, quality=95, size=VIEWPORT)
            await page.wait_for_timeout(int(duration * 1000))
            await page.screencast.stop()
            await context.close()
            await browser.close()

        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(webm),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "30",
            "-t",
            f"{duration:.3f}",
            "-movflags",
            "+faststart",
            "-an",
            str(output_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {stderr.decode(errors='replace')[-1000:]}")


def probe_video(output_path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size,bit_rate:stream=codec_name,width,height,pix_fmt,avg_frame_rate",
            "-of",
            "json",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", type=Path, default=DEFAULT_SCRIPT)
    parser.add_argument("--assets", type=Path, default=DEFAULT_ASSETS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--reuse-captures", action="store_true")
    args = parser.parse_args()

    script = _read_script(args.script)
    if args.reuse_captures:
        stored_captures = json.loads((args.assets / "captures.json").read_text())
        captures_by_id = {capture["id"]: capture for capture in stored_captures}
        captures = [{**captures_by_id[scene["id"]], **scene} for scene in script["scenes"]]
    else:
        captures = await capture_evidence(script, args.assets)
    document, duration = build_composition(script, captures)
    await render_video(document, duration, args.output)
    probe = await asyncio.to_thread(probe_video, args.output)
    print(json.dumps({"output": str(args.output), "probe": probe}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
