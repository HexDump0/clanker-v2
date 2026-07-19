"""Central application configuration.

Every setting the app reads from the environment lives here — modules must take
config (or values from it) as arguments instead of calling ``os.getenv`` themselves.
Loaded from the environment and an optional ``.env`` file at the repo root.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
        description="Dashboard session JWT (the `session` cookie value).",
    )
    shipwrights_workplace: str = "stardance"

    # Watcher
    watcher_poll_interval: float = Field(default=30.0, ge=5.0)
    watcher_state_file: Path = Path("data/watcher_state.json")
    watcher_emit_backlog: bool = Field(
        default=False,
        description=(
            "On the very first run (no state file), whether pending certs already "
            "in the queue are emitted as new (True) or just recorded (False)."
        ),
    )

    def require_session(self) -> str:
        if not self.shipwrights_session:
            raise RuntimeError(
                "SHIPWRIGHTS_SESSION is not set — provide the dashboard session "
                "cookie JWT via the environment or .env"
            )
        return self.shipwrights_session


def load_settings() -> Settings:
    return Settings()
