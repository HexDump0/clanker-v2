"""Central application configuration.

Every setting the app reads from the environment lives here — modules must take
config (or values from it) as arguments instead of calling ``os.getenv`` themselves.
Loaded from the environment and an optional ``.env`` file at the repo root.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

HACKCLUB_AI_BASE_URL = "https://ai.hackclub.com/proxy/v1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Shipwrights Dashboard (ds.shipwrights.dev)
    shipwrights_base_url: str = "https://ds.shipwrights.dev"
    shipwrights_session: str = Field(
        default="",
        description=(
            "Dashboard session JWT. A bare value, `session=...`, or pasted Cookie header "
            "is accepted."
        ),
    )
    shipwrights_workplace: str = "stardance"
    stardance_session: str = Field(
        default="",
        description=(
            "Stardance (stardance.hackclub.com) login cookie value — the "
            "`_stardance_session_4` cookie. Lets fetch_stardance_project "
            "load the auth-gated admin ship page. Value only; a leading "
            "`_stardance_session_4=` prefix is tolerated."
        ),
    )

    # Watcher
    watcher_source: Literal["dashboard", "stardance"] = Field(
        default="dashboard",
        description=(
            "Where the watcher detects new pending ships: 'dashboard' polls the "
            "Shipwrights certifications API; 'stardance' polls the Stardance "
            "admin ship queue (source of truth, needs STARDANCE_SESSION) and "
            "reconciles ships to Dashboard certs by external_id before emitting."
        ),
    )
    watcher_poll_interval: float = Field(default=30.0, ge=5.0)
    watcher_state_file: Path = Path("data/watcher_state.json")
    watcher_emit_backlog: bool = Field(
        default=False,
        description=(
            "On the very first run (no state file), whether pending certs already "
            "in the queue are emitted as new (True) or just recorded (False)."
        ),
    )

    # AI model (review agent)
    ai_provider: Literal["openrouter", "hackclub"] = "openrouter"
    openrouter_api_key: str = ""
    hackclub_api_key: str = ""
    model_name: str = "xiaomi/mimo-v2.5-pro"
    openrouter_provider_only: str = Field(
        default="",
        description=(
            "Comma-separated OpenRouter provider slugs to pin routing to "
            "(e.g. 'alibaba'). Empty = let OpenRouter route freely. "
            "Only honored when ai_provider=openrouter."
        ),
    )
    openrouter_allow_fallbacks: bool = Field(
        default=False,
        description="With a provider pin, whether OpenRouter may fall back to others.",
    )
    reasoning_effort: Literal["low", "medium", "high"] = "medium"
    agent_timeout: float = 120.0

    # Browser render + vision describer (demo "does this look right?" evidence)
    browser_render_enabled: bool = Field(
        default=True,
        description=(
            "Render demo pages in headless Chromium and describe the screenshot "
            "with the vision model. Requires `playwright install chromium`."
        ),
    )
    vision_model_name: str = Field(
        default="qwen/qwen3-vl-8b-thinking",
        description="Vision model that describes rendered page screenshots.",
    )
    video_director_model_name: str = Field(
        default="qwen/qwen3-vl-8b-thinking",
        description=(
            "Separate vision model used once to select and write review-video scenes."
        ),
    )
    video_director_provider_only: str = Field(
        default="",
        description=(
            "Comma-separated OpenRouter provider slugs used only for the video "
            "director model. Empty = let OpenRouter route the director freely; "
            "the review agent's OPENROUTER_PROVIDER_ONLY setting is not inherited."
        ),
    )
    video_director_allow_fallbacks: bool = Field(
        default=False,
        description=(
            "With a video-director provider pin, whether OpenRouter may fall back "
            "to other providers."
        ),
    )
    video_enabled: bool = Field(
        default=True,
        description="Generate a review video when the review supplies browser evidence.",
    )
    video_dir: Path = Path("data/videos")
    video_work_dir: Path = Path("data/video-runs")
    video_music_enabled: bool = Field(
        default=True,
        description="Mix a chill background track into review videos.",
    )
    video_music_file: Path | None = Field(
        default=None,
        description=(
            "Path to a background music file (looped, faded, mixed low) for review "
            "videos. Empty = use the bundled default track. Swap in any royalty-free "
            "track here. Ignored when VIDEO_MUSIC_ENABLED is false."
        ),
    )
    video_timeout: float = Field(
        default=240.0,
        ge=30.0,
        description="Hard timeout for the complete optional video artifact stage.",
    )
    render_timeout: float = Field(
        default=20.0, ge=5.0, description="Page-load timeout (seconds) for browser renders."
    )

    # Reviews
    max_concurrent_reviews: int = Field(default=2, ge=1)
    pdf_dir: Path = Path("data/pdfs")
    github_token: str = Field(
        default="", description="Optional; raises GitHub API rate limits for review tools."
    )

    # Slack
    slack_bot_token: str = ""
    slack_app_token: str = Field(
        default="", description="App-level token for Socket Mode (chat bot)."
    )
    slack_channel: str = Field(
        default="", description="Channel ID for ship announcements and mentions."
    )
    slack_ship_ping: str = Field(
        default="",
        description=(
            "Who to 'cc' on new-ship announcements. A usergroup id (starts with "
            "'S') renders as a group ping, a user id ('U'/'W') as a user ping; any "
            "other value is shown as literal text. Empty = no cc line."
        ),
    )
    slack_daily_ping: str = Field(
        default="",
        description=(
            "Who to 'cc' on the daily queue summary. Same format as "
            "SLACK_SHIP_PING (usergroup 'S...', user 'U...'/'W...', or literal "
            "text). Empty = no cc line."
        ),
    )
    daily_summary_enabled: bool = Field(
        default=True,
        description="Post the daily queue summary to Slack at DAILY_SUMMARY_TIME_UTC.",
    )
    daily_summary_time_utc: str = Field(
        default="23:30",
        description="HH:MM UTC when the daily queue summary is posted.",
    )
    chat_memory_file: Path = Field(
        default=Path("data/chat_memory.json"),
        description=(
            "Where the chat bot persists its simple long-term memory (facts it "
            "chooses to remember about people/projects). Chat-only; never read by "
            "the review pipeline."
        ),
    )
    chat_memory_max_entries: int = Field(
        default=200,
        ge=1,
        description="Cap on chat-memory entries; the oldest is evicted past this.",
    )

    # Observability (optional)
    logfire_token: str = ""
    logfire_service_name: str = "clanker"

    def require_session(self) -> str:
        if not self.shipwrights_session:
            raise RuntimeError(
                "SHIPWRIGHTS_SESSION is not set — provide the dashboard session "
                "cookie JWT via the environment or .env"
            )
        return self.shipwrights_session

    def require_ai_key(self) -> str:
        key = self.hackclub_api_key if self.ai_provider == "hackclub" else self.openrouter_api_key
        if not key:
            name = "HACKCLUB_API_KEY" if self.ai_provider == "hackclub" else "OPENROUTER_API_KEY"
            raise RuntimeError(f"{name} is not set (AI_PROVIDER={self.ai_provider})")
        return key

    def require_slack(self) -> str:
        if not self.slack_bot_token:
            raise RuntimeError("SLACK_BOT_TOKEN is not set")
        if not self.slack_channel:
            raise RuntimeError("SLACK_CHANNEL is not set")
        return self.slack_bot_token

    @property
    def provider_pins(self) -> list[str]:
        return [p.strip() for p in self.openrouter_provider_only.split(",") if p.strip()]

    @property
    def video_director_provider_pins(self) -> list[str]:
        return [
            provider.strip()
            for provider in self.video_director_provider_only.split(",")
            if provider.strip()
        ]


def load_settings() -> Settings:
    return Settings()


def _httpx_excluded_urls(settings: Settings, existing: str = "") -> str:
    """OpenTelemetry URL filters, including the watcher's noisy queue poll."""
    base_url = re.escape(settings.shipwrights_base_url.rstrip("/"))
    workplace = re.escape(settings.shipwrights_workplace)
    pending_poll = (
        rf"^{base_url}/api/v1/workplaces/{workplace}/certifications\?"
        rf"[^#]*status=PENDING(?:&|$)"
    )
    patterns = [pattern.strip() for pattern in existing.split(",") if pattern.strip()]
    if pending_poll not in patterns:
        patterns.append(pending_poll)
    return ",".join(patterns)


def configure_observability(settings: Settings) -> None:
    """Set up logfire if available/configured; a no-op otherwise."""
    import logfire

    logfire.configure(
        service_name=settings.logfire_service_name,
        send_to_logfire="if-token-present",
        token=settings.logfire_token or None,
    )
    logfire.instrument_pydantic_ai()
    # OpenTelemetry's HTTPX integration reads URL exclusions when instrumentation
    # starts. Keep useful HTTP spans while dropping the watcher's repetitive
    # `GET .../certifications?status=PENDING` requests.
    exclusion_variable = "OTEL_PYTHON_HTTPX_EXCLUDED_URLS"
    os.environ[exclusion_variable] = _httpx_excluded_urls(
        settings, os.environ.get(exclusion_variable, "")
    )
    logfire.instrument_httpx()
