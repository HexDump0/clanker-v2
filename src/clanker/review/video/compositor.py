# ruff: noqa: E501
"""Render resolved screenshot scenes into a restrained, deterministic MP4."""

from __future__ import annotations

import asyncio
import base64
import html
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from clanker.review.video.models import ComposedScene, VideoPlan, VideoProject

VIEWPORT = {"width": 1280, "height": 720}
INTRO_SECONDS = 3.0
SCENE_SECONDS = 6.0
OUTRO_SECONDS = 4.0
FADE_SECONDS = 0.35
ENCODE_TIMEOUT = 180.0


class CompositionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RenderedVideo:
    path: Path
    duration_seconds: float
    size_bytes: int


def _data_url(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def _callout_position(scene: ComposedScene) -> str:
    box = scene.target_box
    if box is None:
        return "right:40px;bottom:40px"
    if box.x + box.width / 2 < VIEWPORT["width"] / 2:
        return "right:40px;top:190px"
    return "left:40px;top:190px"


def _scene_html(scene: ComposedScene, index: int, total: int) -> str:
    rect = "null"
    if scene.target_box:
        padding = 10
        box = scene.target_box
        rect = json.dumps(
            {
                "x": max(6, box.x - padding),
                "y": max(6, box.y - padding),
                "w": min(VIEWPORT["width"] - 12, box.width + padding * 2),
                "h": min(VIEWPORT["height"] - 12, box.height + padding * 2),
            }
        )
    fallback = " fallback" if scene.target_box is None else ""
    source = scene.capture.final_url
    return f"""
    <section class="scene evidence{fallback}" data-scene="{index}">
      <img class="capture" src="{_data_url(scene.capture.screenshot_path)}" alt="">
      <canvas width="1280" height="720" data-rect='{html.escape(rect)}'></canvas>
      <article class="callout" style="{_callout_position(scene)}">
        <div class="role">{html.escape(scene.directed.role.value)}</div>
        <h2>{html.escape(scene.directed.title)}</h2>
        <p>{html.escape(scene.directed.explanation)}</p>
      </article>
      <div class="source">{html.escape(source)}</div>
      <div class="index">{index:02d} / {total:02d}</div>
    </section>
    """


def build_composition(
    project: VideoProject, plan: VideoPlan, scenes: list[ComposedScene]
) -> tuple[str, float]:
    if not scenes:
        raise CompositionError("cannot render a video without scenes")
    timeline: list[dict[str, object]] = []
    timeline.append({"selector": ".intro", "start": 0, "end": INTRO_SECONDS + FADE_SECONDS})
    cursor = INTRO_SECONDS
    scene_html: list[str] = []
    for index, scene in enumerate(scenes, 1):
        timeline.append(
            {
                "selector": f'[data-scene="{index}"]',
                "start": cursor,
                "end": cursor + SCENE_SECONDS + FADE_SECONDS,
            }
        )
        scene_html.append(_scene_html(scene, index, len(scenes)))
        cursor += SCENE_SECONDS
    timeline.append({"selector": ".outro", "start": cursor, "end": cursor + OUTRO_SECONDS})
    total = cursor + OUTRO_SECONDS
    fixes = "".join(
        f"<li><span>{index:02d}</span>{html.escape(fix)}</li>"
        for index, fix in enumerate(project.required_fixes, 1)
    ) or "<li><span>01</span>Review the evidence above before resubmitting.</li>"

    document = f"""<!doctype html><html><head><meta charset="utf-8"><style>
* {{ box-sizing: border-box; }}
html, body {{ margin:0; width:1280px; height:720px; overflow:hidden; background:#0b0b0c; }}
body {{ font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif; color:#f4f4f4; }}
.scene {{ position:absolute; inset:0; opacity:0; overflow:hidden; background:#0b0b0c; }}
.intro,.outro {{ display:grid; place-items:center; }}
.intro-inner,.outro-inner {{ width:1000px; }}
.kicker,.role {{ color:#ec3750; font-size:11px; font-weight:800; letter-spacing:.14em; text-transform:uppercase; }}
.intro h1 {{ margin:16px 0 0; max-width:930px; font-size:58px; line-height:1.04; letter-spacing:-.035em; }}
.meta {{ display:flex; gap:14px; align-items:center; margin-top:28px; padding-top:18px; border-top:1px solid #353538; color:#aaaab0; font-size:17px; }}
.meta strong {{ color:#fff; }} .verdict {{ margin-left:auto; color:#ec3750; font-size:13px; font-weight:800; letter-spacing:.12em; }}
.summary {{ max-width:800px; margin-top:16px; color:#b5b5ba; font-size:19px; line-height:1.5; }}
.capture,.evidence canvas {{ position:absolute; inset:0; width:1280px; height:720px; }}
.evidence canvas {{ z-index:1; }}
.callout {{ position:absolute; z-index:2; width:440px; padding:22px 24px; background:#111113; border:1px solid #414146; border-left:3px solid #ec3750; }}
.callout h2 {{ margin:10px 0 10px; font-size:27px; line-height:1.15; letter-spacing:-.02em; }}
.callout p {{ margin:0; color:#c2c2c7; font-size:16px; line-height:1.48; }}
.fallback .callout {{ width:470px; }}
.source {{ position:absolute; z-index:3; left:20px; bottom:17px; max-width:720px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; padding:7px 10px; background:#111113; border:1px solid #343438; color:#aaaab0; font-size:11px; }}
.index {{ position:absolute; z-index:3; right:20px; bottom:20px; color:#b0b0b4; font-size:11px; letter-spacing:.13em; }}
.outro-inner {{ display:grid; grid-template-columns:.8fr 1.2fr; gap:75px; align-items:start; }}
.outro h2 {{ margin:14px 0 0; font-size:46px; line-height:1.08; letter-spacing:-.03em; }}
.outro ul {{ list-style:none; margin:0; padding:0; }}
.outro li {{ display:grid; grid-template-columns:44px 1fr; gap:14px; padding:18px 0; border-top:1px solid #353538; font-size:19px; line-height:1.4; }}
.outro li:last-child {{ border-bottom:1px solid #353538; }}
.outro li span {{ color:#ec3750; font-size:12px; font-weight:800; padding-top:6px; }}
</style></head><body>
<section class="scene intro"><div class="intro-inner"><div class="kicker">SW-CLANKER REVIEW</div><h1>{html.escape(plan.headline)}</h1><div class="meta"><strong>{html.escape(project.project_name)}</strong><span>{html.escape(project.project_author)}</span><span class="verdict">{html.escape(project.verdict)}</span></div><div class="summary">{html.escape(plan.summary)}</div></div></section>
{"".join(scene_html)}
<section class="scene outro"><div class="outro-inner"><div><div class="kicker">Before resubmitting</div><h2>Required<br>fixes.</h2></div><ul>{fixes}</ul></div></section>
<script>
const timeline={json.dumps(timeline)}; const fade={FADE_SECONDS}; const started=performance.now();
const clamp=(n,lo,hi)=>Math.max(lo,Math.min(hi,n));
function paint(canvas) {{
  const rect=JSON.parse(canvas.dataset.rect); const ctx=canvas.getContext('2d');
  ctx.clearRect(0,0,1280,720); if (!rect) return;
  ctx.fillStyle='rgba(6,6,10,.66)'; ctx.fillRect(0,0,1280,720);
  ctx.clearRect(rect.x,rect.y,rect.w,rect.h);
  ctx.strokeStyle='#ec3750'; ctx.lineWidth=2; ctx.strokeRect(rect.x+1,rect.y+1,rect.w-2,rect.h-2);
}}
for (const canvas of document.querySelectorAll('canvas')) paint(canvas);
function frame(now) {{ const t=(now-started)/1000; for (const item of timeline) {{
  const node=document.querySelector(item.selector); const a=clamp((t-item.start)/fade,0,1); const b=clamp((item.end-t)/fade,0,1); node.style.opacity=Math.min(a,b);
}} requestAnimationFrame(frame); }} requestAnimationFrame(frame);
</script></body></html>"""
    return document, total


async def render_composition(document: str, duration: float, output_path: Path) -> RenderedVideo:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="clanker-video-compose-") as tmp:
        webm = Path(tmp) / "capture.webm"
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise CompositionError("playwright is not installed") from None
        async with async_playwright() as playwright:
            try:
                browser = await playwright.chromium.launch(headless=True, channel="chromium")
            except Exception:
                browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context(viewport=VIEWPORT, screen=VIEWPORT)
                page = await context.new_page()
                await page.set_content(document, wait_until="load")
                await page.screencast.start(path=webm, quality=95, size=VIEWPORT)
                await page.wait_for_timeout(round(duration * 1000))
                await page.screencast.stop()
                await context.close()
            finally:
                await browser.close()

        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-v", "error", "-i", str(webm),
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p", "-r", "30", "-t", f"{duration:.3f}",
            "-movflags", "+faststart", "-an", str(output_path),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=ENCODE_TIMEOUT)
        except TimeoutError:
            process.kill()
            raise CompositionError("ffmpeg timed out") from None
        if process.returncode != 0:
            raise CompositionError(f"ffmpeg failed: {stderr.decode(errors='replace')[-800:]}")
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise CompositionError("encoder produced no output")
    return RenderedVideo(output_path, duration, output_path.stat().st_size)
