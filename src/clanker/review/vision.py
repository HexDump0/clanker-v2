"""Vision describer: turn a rendered-page screenshot into a detailed description.

The vision model is deliberately a *describer*, not a judge — it reports what
is visible on the screen and nothing else. The review agent, which has the full
submission context (README, commits, claimed project type, prior reviews),
draws its own conclusions from the description. Keeping the verdict with the
agent avoids inheriting confident misreads from a model that lacks context.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic_ai import Agent, BinaryContent
from pydantic_ai.models.openrouter import OpenRouterModelSettings

from clanker.config import Settings
from clanker.llm import build_model
from clanker.review.browser import render_page

logger = logging.getLogger(__name__)

VISION_INSTRUCTIONS = """\
You describe screenshots of web pages for a project reviewer who cannot see the
image. Describe what you see in detail: the overall layout, headings and other
visible text, navigation, interactive elements (buttons, forms, inputs), images
or graphics, and anything else notable — including large blank areas, error
messages, overlays or banners covering content, and sections that look
unfinished or placeholder-like. Be factual, specific, and thorough. Describe
what is visible; do not judge whether the site or app works correctly.
"""


def create_vision_agent(settings: Settings) -> Agent:
    return Agent(
        build_model(settings, settings.vision_model_name),
        instructions=VISION_INSTRUCTIONS,
        model_settings=OpenRouterModelSettings(timeout=settings.agent_timeout),
    )


class PageRenderer:
    """Render a page in headless Chromium and describe its screenshot.

    Produces the JSON-able payload shared by the ``render_page`` tool
    and the packet's pre-fetched demo render section.
    """

    def __init__(self, settings: Settings, *, agent: Agent | None = None) -> None:
        self._agent = agent or create_vision_agent(settings)
        self._timeout = settings.render_timeout

    async def render_payload(self, url: str) -> dict[str, Any]:
        result = await render_page(url, load_timeout=self._timeout)
        if not result.ok:
            return {"ok": False, "url": url, "error": result.error}
        payload: dict[str, Any] = {
            "ok": True,
            "url": url,
            "final_url": result.final_url,
            "status_code": result.status_code,
            "reachable": result.status_code is not None and 200 <= result.status_code < 400,
            "viewport_mostly_empty": result.viewport_mostly_empty,
            "rendered_text": result.text,
        }
        if result.screenshot:
            try:
                described = await self._agent.run(
                    [
                        "Describe this screenshot of the page in detail.",
                        BinaryContent(data=result.screenshot, media_type="image/jpeg"),
                    ]
                )
                payload["screenshot_description"] = described.output
            except Exception as e:
                # A described render is better, but the hard signals still stand.
                logger.warning("Vision description failed for %s: %s", url, e)
                payload["screenshot_description"] = None
                payload["vision_error"] = str(e)
        return payload

    async def render_json(self, url: str) -> str:
        return json.dumps(await self.render_payload(url))
