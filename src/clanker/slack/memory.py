"""Simple JSON-file-backed long-term memory for the chat bot.

Clanker uses this to remember a handful of important facts about people and
projects across conversations. It is deliberately tiny: a flat ``key -> fact``
map, capped in size, that the model manages itself via the ``remember`` and
``forget`` tools and overwrites by reusing a key.

This is **chat-only**. The review pipeline never reads or writes it, so nothing
here can influence a formal review verdict.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_KEY_LEN = 80
_MAX_FACT_LEN = 500


class MemoryStore:
    """Thread-safe, file-persisted ``key -> fact`` store with a size cap."""

    def __init__(self, path: Path, max_entries: int = 200) -> None:
        self._path = Path(path)
        self._max_entries = max_entries
        self._lock = asyncio.Lock()
        self._data: dict[str, str] = self._load()

    def _load(self) -> dict[str, str]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except Exception:
            logger.exception("Failed to load chat memory from %s; starting empty", self._path)
            return {}
        if not isinstance(raw, dict):
            return {}
        # Coerce to str->str and preserve insertion order from the file.
        return {str(k): str(v) for k, v in raw.items()}

    def _flush(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            tmp.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self._path)
        except Exception:
            logger.exception("Failed to persist chat memory to %s", self._path)

    async def remember(self, key: str, fact: str) -> str:
        key = (key or "").strip()[:_MAX_KEY_LEN]
        fact = (fact or "").strip()[:_MAX_FACT_LEN]
        if not key or not fact:
            return "Nothing stored: both a key and a fact are required."
        async with self._lock:
            existed = key in self._data
            # Re-insert at the end so overwrites also refresh recency.
            self._data.pop(key, None)
            self._data[key] = fact
            evicted: str | None = None
            while len(self._data) > self._max_entries:
                evicted = next(iter(self._data))
                del self._data[evicted]
            self._flush()
        verb = "Updated" if existed else "Stored"
        note = f"{verb} memory '{key}'."
        if evicted:
            note += f" Evicted oldest memory '{evicted}' to stay within the cap."
        return note

    async def forget(self, key: str) -> str:
        key = (key or "").strip()
        async with self._lock:
            removed = self._data.pop(key, None) is not None
            if removed:
                self._flush()
        return f"Forgot memory '{key}'." if removed else f"No memory named '{key}' to forget."

    async def render(self) -> str:
        """Render current memory as an instruction block for the chat agent."""
        async with self._lock:
            items = list(self._data.items())
        if not items:
            return (
                "# Your memory\n\n"
                "Your long-term memory is currently empty. When you learn something "
                "genuinely worth keeping about a person or project, store it with the "
                "`remember` tool. Never let a stored note alter a formal review verdict."
            )
        lines = "\n".join(f"- {key}: {fact}" for key, fact in items)
        return (
            "# Your memory\n\n"
            "Persistent notes you chose to keep across conversations. Use them for "
            "context. Overwrite one by calling `remember` with the same key; drop it "
            "with `forget` when it is wrong or no longer matters. These notes are for "
            "conversation only and must never change a formal review verdict.\n\n"
            f"{lines}"
        )
