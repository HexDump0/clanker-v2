"""Shared LLM model factory.

Lives outside ``review.agent`` so modules like ``review.vision`` can build
models without importing the agent module (which imports the tools, which
import vision — a cycle otherwise).
"""

from __future__ import annotations

from openai import AsyncOpenAI
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from clanker.config import HACKCLUB_AI_BASE_URL, Settings


def build_model(settings: Settings, model_name: str | None = None) -> OpenRouterModel:
    """An LLM via OpenRouter directly or the Hack Club AI proxy.

    ``model_name`` overrides ``settings.model_name`` (e.g. the vision model).
    """
    if settings.ai_provider == "hackclub":
        client = AsyncOpenAI(base_url=HACKCLUB_AI_BASE_URL, api_key=settings.require_ai_key())
        provider = OpenRouterProvider(openai_client=client)
    else:
        provider = OpenRouterProvider(api_key=settings.require_ai_key())
    return OpenRouterModel(model_name or settings.model_name, provider=provider)
