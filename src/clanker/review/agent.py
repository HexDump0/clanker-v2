"""pydantic-ai agent factories.

Two agents share the same model and toolset:

- the **review agent** runs one cert review and must return a validated
  ``ReviewOutput`` via prompted JSON (no forced output-tool call, message-log
  scraping, or prompt-pleading for a PDF tool call);
- the **chat agent** answers Slack mentions in plain markdown and can trigger
  full reviews through an injected tool.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from pydantic_ai import Agent, PromptedOutput
from pydantic_ai.models.openrouter import OpenRouterModelSettings

from clanker.config import Settings
from clanker.llm import build_model
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
        # A bare Pydantic model uses tool output by default. That makes
        # pydantic-ai force `tool_choice=required`, which Alibaba rejects when
        # reasoning/thinking is enabled. Prompted output keeps ordinary review
        # tools optional while retaining Pydantic validation and retries.
        output_type=PromptedOutput(ReviewOutput),
        instructions=build_review_instructions(),
        model_settings=build_model_settings(settings),
        tools=tools.all(),
        retries=4,
    )


def build_chat_instructions() -> str:
    """Instructions for the @-mention chat bot.

    Starts with the Clanker personality prompt, then appends the reviewer rubric,
    pre-check gates, and demo guidelines as *reference* knowledge so the chat bot
    can answer questions about what is and isn't allowed. It does NOT get the
    stage-by-stage "perform a review" framing — formal reviews run through the
    separate review agent via the injected ``run_review`` tool.
    """
    return "\n\n".join(
        [
            _prompt("chat.md"),
            "## The rubric (checks)\n\n" + _prompt("checks.md"),
            "## Pre-check gates (instant-reject conditions)\n\n" + _prompt("precheck.md"),
            "## Demo guidelines\n\n" + _prompt("demo_guidelines.md"),
        ]
    )


def create_chat_agent(
    settings: Settings,
    tools: ReviewTools,
    extra_tools: list[Callable] | None = None,
    memory_provider: Callable[[], Awaitable[str]] | None = None,
) -> Agent:
    agent = Agent(
        build_model(settings),
        instructions=build_chat_instructions(),
        model_settings=build_model_settings(settings),
        tools=tools.all() + list(extra_tools or []),
    )
    if memory_provider is not None:
        # Dynamic instruction: re-read the persistent memory on every run so
        # newly remembered facts show up immediately. Chat-only — the review
        # agent has no memory instruction and is unaffected.
        @agent.instructions
        async def _memory_block() -> str:
            return await memory_provider()

    return agent
