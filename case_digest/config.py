from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from .models import SourceConfig, SourceKind


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str | None = None
    tavily_api_key: str | None = None
    telegram_token: str | None = None
    telegram_chat_id: str | None = None
    api_id: int | None = None
    api_hash: str | None = None
    session_string: str | None = None
    openrouter_model: str = "anthropic/claude-haiku-4.5"

    @classmethod
    def from_env(cls) -> "Settings":
        api_id = os.getenv("API_ID")
        return cls(
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
            tavily_api_key=os.getenv("TAVILY_API_KEY"),
            telegram_token=os.getenv("TELEGRAM_TOKEN"),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
            api_id=int(api_id) if api_id else None,
            api_hash=os.getenv("API_HASH"),
            session_string=os.getenv("SESSION_STRING"),
            openrouter_model=os.getenv("OPENROUTER_MODEL", "anthropic/claude-haiku-4.5"),
        )


def load_sources(path: Path) -> list[SourceConfig]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    sources: list[SourceConfig] = []
    for item in raw.get("web", []):
        sources.append(SourceConfig.model_validate(item))
    for item in raw.get("telegram", []):
        sources.append(SourceConfig.model_validate({**item, "kind": SourceKind.TELEGRAM}))
    return sources

