"""Headless-browser page rendering for demo "does this look right?" evidence.

One-shot render, not a browser agent: load the page with JavaScript enabled,
grab the post-render visible text and a viewport screenshot, and close. Runs
with the isolation the v2 architecture plan demands for browser work — a fresh
incognito context per render, fixed viewport, no cookies or credentials of any
kind, downloads refused, and a hard timeout. Submitted sites are untrusted.
"""

from __future__ import annotations

from dataclasses import dataclass

TEXT_LIMIT = 20000
VIEWPORT = {"width": 1280, "height": 800}
# Below this many visible characters the viewport is flagged as mostly empty —
# the classic signature of a crashed CSR app or an unfinished deploy.
EMPTY_TEXT_THRESHOLD = 40


@dataclass(slots=True)
class RenderResult:
    ok: bool
    url: str
    final_url: str | None = None
    status_code: int | None = None
    text: str = ""
    viewport_mostly_empty: bool = False
    screenshot: bytes | None = None  # JPEG
    error: str | None = None


async def render_page(url: str, *, load_timeout: float = 20.0) -> RenderResult:
    """Render ``url`` in headless Chromium; never raises — errors are data."""
    if not url or not url.startswith(("http://", "https://")):
        return RenderResult(ok=False, url=url, error=f"Invalid URL: {url}")
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return RenderResult(ok=False, url=url, error="playwright is not installed")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(viewport=VIEWPORT, accept_downloads=False)
                context.set_default_timeout(load_timeout * 1000)
                page = await context.new_page()
                response = await page.goto(url, wait_until="load", timeout=load_timeout * 1000)
                # Give SPAs a moment to hydrate; don't hang on pages that poll forever.
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                try:
                    text = (await page.inner_text("body")).strip()
                except Exception:
                    text = ""
                screenshot = await page.screenshot(type="jpeg", quality=70)
                return RenderResult(
                    ok=True,
                    url=url,
                    final_url=page.url,
                    status_code=response.status if response else None,
                    text=text[:TEXT_LIMIT],
                    viewport_mostly_empty=len(text) < EMPTY_TEXT_THRESHOLD,
                    screenshot=screenshot,
                )
            finally:
                await browser.close()
    except Exception as e:
        return RenderResult(ok=False, url=url, error=f"Render failed: {e}")
