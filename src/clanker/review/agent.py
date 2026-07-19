"""pydantic-ai agent factories.

Two agents share the same model and toolset:

- the **review agent** runs one cert review and must return a validated
  ``ReviewOutput`` (``output_type`` — no message-log scraping, no prompt-pleading
  for a PDF tool call);
- the **chat agent** answers Slack mentions in plain markdown and can trigger
  full reviews through an injected tool.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.models.openrouter import OpenRouterModel, OpenRouterModelSettings
from pydantic_ai.providers.openrouter import OpenRouterProvider

from clanker.config import HACKCLUB_AI_BASE_URL, Settings
from clanker.review.models import ReviewOutput
from clanker.review.tools import ReviewTools

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def build_review_instructions() -> str:
    return "\n\n---\n\n".join(
        [
            _prompt("system.md"),
            "# Stage 1: Pre-Check\n\n" + _prompt("precheck.md"),
            "# Stage 2: Checks\n\n" + _prompt("checks.md"),
            "# Stage 3: Verdict\n\n" + _prompt("reviewer.md"),
            "# Demo Guidelines Reference\n\n" + _prompt("demo_guidelines.md"),
        ]
    )


def build_model(settings: Settings) -> OpenRouterModel:
    """The LLM, via OpenRouter directly or the Hack Club AI proxy."""
    if settings.ai_provider == "hackclub":
        client = AsyncOpenAI(base_url=HACKCLUB_AI_BASE_URL, api_key=settings.require_ai_key())
        provider = OpenRouterProvider(openai_client=client)
    else:
        provider = OpenRouterProvider(api_key=settings.require_ai_key())
    return OpenRouterModel(settings.model_name, provider=provider)


def build_model_settings(settings: Settings) -> OpenRouterModelSettings:
    model_settings = OpenRouterModelSettings(
        timeout=settings.agent_timeout,
        openrouter_reasoning={"effort": settings.reasoning_effort},
    )
    # Provider pinning (e.g. OPENROUTER_PROVIDER_ONLY=alibaba) — only meaningful
    # when talking to OpenRouter directly.
    if settings.provider_pins and settings.ai_provider == "openrouter":
        model_settings["openrouter_provider"] = {
            "only": settings.provider_pins,
            "allow_fallbacks": settings.openrouter_allow_fallbacks,
        }
    return model_settings


def create_review_agent(settings: Settings, tools: ReviewTools) -> Agent[None, ReviewOutput]:
    return Agent(
        build_model(settings),
        output_type=ReviewOutput,
        instructions=build_review_instructions(),
        model_settings=build_model_settings(settings),
        tools=tools.all(),
        retries=4,
    )


CHAT_EXTRA_INSTRUCTIONS = """
# Chat mode

You are talking to Shipwright reviewers in Slack. Answer questions, investigate
projects with your tools, and be concise — this is a chat, not a report.

To run a complete formal review of a cert, call the `run_review` tool with the cert
id; it executes the whole pipeline (all stages, PDF report) and returns the verdict.
Don't simulate the pipeline by hand in chat.
"""


def create_chat_agent(
    settings: Settings,
    tools: ReviewTools,
    extra_tools: list[Callable] | None = None,
) -> Agent:
    return Agent(
        build_model(settings),
        instructions=build_review_instructions() + CHAT_EXTRA_INSTRUCTIONS,
        model_settings=build_model_settings(settings),
        tools=tools.all() + list(extra_tools or []),
    )
