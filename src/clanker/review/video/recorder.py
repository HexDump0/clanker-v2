"""Deterministic replay of a ``VideoScript`` into a recorded MP4.

Pass 2 of the video pipeline: no model, no decisions. Opens each scene's URL
in one recorded Playwright page, injects the overlay, holds, moves on. A scene
whose page or target fails is skipped and reported — the rest of the video
still renders. Same isolation rules as review/browser.py: fresh context, no
credentials, downloads refused, fixed viewport, hard per-page timeout.
"""

from __future__ import annotations

import asyncio
import html
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from clanker.review.video.models import Scene, VideoScript
from clanker.review.video.overlay import OVERLAY_JS

logger = logging.getLogger(__name__)

VIEWPORT = {"width": 1280, "height": 800}
SCROLL_SETTLE_SECONDS = 1.4
FADE_SECONDS = 0.6
TITLE_CARD_SECONDS = 3.5
OUTRO_MIN_SECONDS = 4.0
ENCODE_TIMEOUT = 120.0

CARD_CSS = """
  html { background: #0d0d12; }
  body {
    margin: 0; height: 100vh; display: flex; align-items: center; justify-content: center;
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif; color: #e8e8ec;
  }
  .wrap { max-width: 760px; padding: 0 48px; }
  .badge { color: #ec3750; font-weight: 700; letter-spacing: 2px; font-size: 14px; }
  h1 { font-size: 52px; margin: 14px 0 6px; color: #fff; }
  .verdict {
    display: inline-block; margin-top: 10px; padding: 6px 18px; border-radius: 8px;
    border: 2px solid #ec3750; color: #ec3750; font-weight: 800; font-size: 22px;
    letter-spacing: 1px;
  }
  .sub { margin-top: 18px; font-size: 18px; color: #c9c9d2; line-height: 1.5; }
  h2 { color: #ec3750; font-size: 30px; margin: 0 0 18px; }
  ul { font-size: 19px; line-height: 1.75; color: #e8e8ec; padding-left: 26px; }
"""


class VideoError(RuntimeError):
    pass


@dataclass(slots=True)
class RecordingResult:
    path: Path
    skipped_scenes: list[str] = field(default_factory=list)


def _title_card_html(script: VideoScript) -> str:
    summary = html.escape(script.summary) if script.summary else ""
    return f"""<style>{CARD_CSS}</style><div class="wrap">
      <div class="badge">SW-CLANKER REVIEW</div>
      <h1>{html.escape(script.project_name)}</h1>
      <div class="verdict">{html.escape(script.verdict)}</div>
      <div class="sub">{summary}</div></div>"""


def _outro_card_html(script: VideoScript) -> str:
    items = "".join(f"<li>{html.escape(fix)}</li>" for fix in script.required_fixes)
    return f"""<style>{CARD_CSS}</style><div class="wrap">
      <div class="badge">SW-CLANKER REVIEW · {html.escape(script.project_name)}</div>
      <h2>Required fixes</h2><ul>{items}</ul></div>"""


async def _play_scene(page, scene: Scene, load_timeout: float) -> None:
    await page.goto(scene.url, wait_until="load", timeout=load_timeout * 1000)
    try:
        await page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass
    await page.evaluate(OVERLAY_JS)
    found = await page.evaluate(
        "spec => window.__clankerOverlay.locate(spec)",
        scene.target.model_dump(),
    )
    if not found:
        raise VideoError(f"target not found on {scene.url}: {scene.target!r}")
    await asyncio.sleep(SCROLL_SETTLE_SECONDS)
    await page.evaluate("([t, b]) => window.__clankerOverlay.draw(t, b)", [scene.title, scene.body])
    await asyncio.sleep(scene.hold_seconds)
    await page.evaluate("() => window.__clankerOverlay.hide()")
    await asyncio.sleep(FADE_SECONDS)


async def _encode_mp4(webm: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-y",
        "-i",
        str(webm),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        "23",
        "-movflags",
        "+faststart",
        "-an",
        str(output),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=ENCODE_TIMEOUT)
    except TimeoutError:
        proc.kill()
        raise VideoError(f"ffmpeg timed out after {ENCODE_TIMEOUT}s") from None
    if proc.returncode != 0:
        raise VideoError(f"ffmpeg failed: {stderr.decode(errors='replace')[-500:]}")
    if not output.exists() or output.stat().st_size == 0:
        raise VideoError("ffmpeg produced no output")


async def record_video_script(
    script: VideoScript, output_path: Path, *, load_timeout: float = 20.0
) -> RecordingResult:
    """Replay ``script`` in a recorded browser and encode the result as MP4."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise VideoError("playwright is not installed") from None

    skipped: list[str] = []
    with tempfile.TemporaryDirectory(prefix="clanker-video-") as tmp:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            try:
                context = await browser.new_context(
                    viewport=VIEWPORT,
                    accept_downloads=False,
                    record_video_dir=tmp,
                    record_video_size=VIEWPORT,
                )
                page = await context.new_page()

                await page.set_content(_title_card_html(script))
                await asyncio.sleep(TITLE_CARD_SECONDS)

                for scene in script.scenes:
                    try:
                        await _play_scene(page, scene, load_timeout)
                    except Exception as e:
                        logger.warning("Skipping scene %r: %s", scene.title, e)
                        skipped.append(scene.title)

                if script.required_fixes:
                    await page.set_content(_outro_card_html(script))
                    await asyncio.sleep(max(OUTRO_MIN_SECONDS, 1.5 * len(script.required_fixes)))

                video = page.video
                await context.close()  # flushes the recording to disk
                webm = Path(await video.path())
            finally:
                await browser.close()

        if len(skipped) == len(script.scenes):
            raise VideoError(f"every scene was skipped: {skipped}")
        await _encode_mp4(webm, output_path)

    return RecordingResult(path=output_path, skipped_scenes=skipped)
