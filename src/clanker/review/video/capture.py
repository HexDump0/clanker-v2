"""Capture clean evidence screenshots and same-state visible DOM geometry.

This module captures the URL supplied by the completed review exactly once and records
what the browser displayed. Review validity remains the review agent's responsibility.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import logfire

from clanker.review.models import VideoEvidence
from clanker.review.video.models import Box, EvidenceCapture, VisibleElement

VIEWPORT = {"width": 1280, "height": 720}

FREEZE_CSS = """
*, *::before, *::after {
  animation: none !important;
  transition: none !important;
  caret-color: transparent !important;
  scroll-behavior: auto !important;
}
"""

# Small, explicit cleanup adapters for known navigation chrome that can obscure
# evidence without being part of the reviewed page. Do not apply broad dialog/banner
# removal: a modal or banner may itself be the evidence.
CLEANUP_CSS_BY_HOST = {
    "github.com": ".auth-form-body.Popover { display: none !important; }",
}

DOM_SNAPSHOT_JS = r"""
() => {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const skipped = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'SVG', 'PATH']);
  const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
  const rows = [];
  for (const element of document.body.querySelectorAll('*')) {
    if (skipped.has(element.tagName)) continue;
    const style = getComputedStyle(element);
    if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) {
      continue;
    }
    const rect = element.getBoundingClientRect();
    const left = Math.max(0, rect.left);
    const top = Math.max(0, rect.top);
    const right = Math.min(vw, rect.right);
    const bottom = Math.min(vh, rect.bottom);
    if (right - left < 2 || bottom - top < 2) continue;
    let text = element.tagName === 'IMG' ? element.getAttribute('alt') : element.innerText;
    text = clean(text);
    if (!text || text.length > 1000) continue;
    rows.push({
      text,
      tag: element.tagName.toLowerCase(),
      box: {x: left, y: top, width: right - left, height: bottom - top},
    });
  }
  // Browsers render text/plain responses as one large <pre> text node. Capture
  // individual non-empty lines so a director-selected README phrase still has
  // precise geometry instead of forcing a whole-page fallback.
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode() && rows.length < 2500) {
    const node = walker.currentNode;
    if (!node.parentElement || !['PRE', 'CODE'].includes(node.parentElement.tagName)) continue;
    let offset = 0;
    for (const rawLine of node.data.split('\n')) {
      const lineStart = offset;
      offset += rawLine.length + 1;
      const text = clean(rawLine);
      if (!text || text.length > 500) continue;
      const leading = rawLine.length - rawLine.trimStart().length;
      const range = document.createRange();
      range.setStart(node, Math.min(lineStart + leading, node.length));
      range.setEnd(node, Math.min(lineStart + rawLine.length, node.length));
      const rect = range.getBoundingClientRect();
      const left = Math.max(0, rect.left);
      const top = Math.max(0, rect.top);
      const right = Math.min(vw, rect.right);
      const bottom = Math.min(vh, rect.bottom);
      if (right - left < 2 || bottom - top < 2) continue;
      rows.push({
        text,
        tag: node.parentElement.tagName.toLowerCase(),
        box: {x: left, y: top, width: right - left, height: bottom - top},
      });
    }
  }
  return rows.slice(0, 2500);
}
"""

INJECT_STYLE_JS = """
css => {
  const style = document.createElement('style');
  style.textContent = css;
  document.documentElement.appendChild(style);
}
"""


class CaptureError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CapturePolicy:
    load_timeout: float = 20.0
    settle_seconds: float = 1.0
    operation_timeout: float = 45.0
    allow_private_hosts: bool = False


DEFAULT_CAPTURE_POLICY = CapturePolicy()


async def _host_is_public(hostname: str) -> bool:
    if hostname.lower() == "localhost" or hostname.lower().endswith(".local"):
        return False
    try:
        literal = ipaddress.ip_address(hostname)
        return literal.is_global
    except ValueError:
        pass
    try:
        results = await asyncio.to_thread(socket.getaddrinfo, hostname, None)
    except OSError:
        return False
    addresses = {item[4][0].split("%", 1)[0] for item in results}
    return bool(addresses) and all(ipaddress.ip_address(address).is_global for address in addresses)


async def validate_capture_url(url: str, *, allow_private_hosts: bool = False) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise CaptureError(f"unsupported evidence URL: {url}")
    if parsed.username or parsed.password:
        raise CaptureError("evidence URLs may not contain credentials")
    if not allow_private_hosts and not await _host_is_public(parsed.hostname):
        raise CaptureError(f"evidence URL does not resolve exclusively to public IPs: {url}")


async def capture_evidence(
    evidence: VideoEvidence,
    output_dir: Path,
    *,
    policy: CapturePolicy = DEFAULT_CAPTURE_POLICY,
) -> EvidenceCapture:
    """Capture one evidence URL without interpreting the review finding."""
    await validate_capture_url(evidence.url, allow_private_hosts=policy.allow_private_hosts)
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise CaptureError("playwright is not installed") from None

    output_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = output_dir / f"{evidence.id}.png"
    host_cache: dict[str, bool] = {}

    async with async_playwright() as playwright:
        try:
            browser = await playwright.chromium.launch(headless=True, channel="chromium")
        except Exception:
            browser = await playwright.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                viewport=VIEWPORT,
                screen=VIEWPORT,
                reduced_motion="reduce",
                service_workers="block",
                accept_downloads=False,
            )

            async def guard_route(route) -> None:
                parsed = urlparse(route.request.url)
                if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                    await route.continue_()
                    return
                allowed = host_cache.get(parsed.hostname)
                if allowed is None:
                    allowed = policy.allow_private_hosts or await _host_is_public(parsed.hostname)
                    host_cache[parsed.hostname] = allowed
                if allowed:
                    await route.continue_()
                else:
                    await route.abort("blockedbyclient")

            await context.route("**/*", guard_route)
            page = await context.new_page()
            page.set_default_timeout(policy.load_timeout * 1000)
            response = await page.goto(
                evidence.url,
                wait_until="domcontentloaded",
                timeout=policy.load_timeout * 1000,
            )
            await validate_capture_url(page.url, allow_private_hosts=policy.allow_private_hosts)
            await page.wait_for_timeout(int(policy.settle_seconds * 1000))
            await page.evaluate(INJECT_STYLE_JS, FREEZE_CSS)
            host = urlparse(page.url).hostname or ""
            if cleanup_css := CLEANUP_CSS_BY_HOST.get(host):
                await page.evaluate(INJECT_STYLE_JS, cleanup_css)
            await page.wait_for_timeout(50)
            raw_elements = await page.evaluate(DOM_SNAPSHOT_JS)
            await page.screenshot(
                path=screenshot_path,
                type="png",
                animations="disabled",
                caret="hide",
                scale="css",
            )
            page_title = await page.title()
            logfire.info(
                "Browser screenshot captured for {evidence_id}",
                evidence_id=evidence.id,
                requested_url=evidence.url,
                final_url=page.url,
                http_status=response.status if response else None,
                screenshot_path=str(screenshot_path),
                screenshot_bytes=screenshot_path.stat().st_size,
                visible_elements=len(raw_elements),
            )
            return EvidenceCapture(
                evidence_id=evidence.id,
                requested_url=evidence.url,
                final_url=page.url,
                http_status=response.status if response else None,
                page_title=page_title,
                captured_at=datetime.now(UTC),
                screenshot_path=screenshot_path,
                viewport_width=VIEWPORT["width"],
                viewport_height=VIEWPORT["height"],
                elements=[
                    VisibleElement(text=item["text"], tag=item["tag"], box=Box(**item["box"]))
                    for item in raw_elements
                ],
            )
        except CaptureError:
            raise
        except Exception as exc:
            raise CaptureError(f"capture failed for {evidence.url}: {exc}") from exc
        finally:
            try:
                await asyncio.wait_for(browser.close(), timeout=5)
            except Exception:
                pass
