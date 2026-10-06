"""Settings, read from environment variables so nothing is hard-coded."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    name: str            # what the assistant calls itself
    model: str           # Ollama model tag; must support tool calling
    ollama_host: str     # where the Ollama server is listening
    db_path: Path        # SQLite file holding chat history, to-dos, notes, reminders
    units: str           # "imperial" (°F, mph) or "metric" (°C, km/h)
    history_limit: int   # how many past messages the model sees each turn


def load_config() -> Config:
    units = os.environ.get("ASSISTANT_UNITS", "imperial").strip().lower()
    if units not in ("imperial", "metric"):
        units = "imperial"
    return Config(
        name=os.environ.get("ASSISTANT_NAME", "Jarvis"),
        model=os.environ.get("ASSISTANT_MODEL", "llama3.2"),
        ollama_host=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
        db_path=Path(os.environ.get("ASSISTANT_DB", PROJECT_ROOT / "data" / "assistant.db")),
        units=units,
        history_limit=int(os.environ.get("ASSISTANT_HISTORY", "30")),
    )
