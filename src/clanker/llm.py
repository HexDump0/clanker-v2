"""Shared LLM model factory.

Lives outside ``review.agent`` so modules like ``review.vision`` can build
models without importing the agent module (which imports the tools, which
import vision — a cycle otherwise).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from openai import AsyncOpenAI
from pydantic_ai.models.openrouter import (
    OpenRouterModel,
    OpenRouterModelSettings,
    OpenRouterProviderConfig,
)
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


def build_provider_config(
    settings: Settings,
    *,
    pins: Sequence[str] = (),
    allow_fallbacks: bool | None = None,
) -> OpenRouterProviderConfig:
    """Build upstream routing accepted by OpenRouter and the Hack Club AI proxy.

    Without an explicit allowlist, the gateway continuously chooses among the
    providers it actually has available using current performance data. Latency is
    a soft preference so a temporary slowdown does not make the model unavailable;
    price is a hard ceiling.
    """
    if pins:
        return {
            "only": list(pins),
            "allow_fallbacks": bool(allow_fallbacks),
        }

    # Pydantic AI 2.13 predates OpenRouter's preferred_max_latency type field,
    # but forwards the provider mapping unchanged. Hack Club AI also accepts it.
    return cast(
        OpenRouterProviderConfig,
        {
            "sort": settings.provider_sort,
            "preferred_max_latency": settings.provider_preferred_max_latency,
            "max_price": {
                "prompt": settings.provider_max_prompt_price,
                "completion": settings.provider_max_completion_price,
            },
            "require_parameters": True,
            "allow_fallbacks": True,
        },
    )


def build_routing_model_settings(
    settings: Settings,
    *,
    pins: Sequence[str] = (),
    allow_fallbacks: bool | None = None,
) -> OpenRouterModelSettings:
    """Base timeout and dynamic provider policy shared by every model workload."""
    return OpenRouterModelSettings(
        timeout=settings.agent_timeout,
        openrouter_provider=build_provider_config(
            settings,
            pins=pins,
            allow_fallbacks=allow_fallbacks,
        ),
    )
