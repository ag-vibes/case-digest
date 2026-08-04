from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from .models import Candidate, SourceConfig, SourceHealth, SourceKind
from .pyrogram_compat import Client, FloodWait

LOGGER = logging.getLogger(__name__)


class TelegramReader:
    def __init__(self, api_id: int, api_hash: str, session_string: str):
        self.client = Client(
            "case_digest_reader",
            api_id=api_id,
            api_hash=api_hash,
            session_string=session_string,
            in_memory=True,
        )

    def collect(
        self,
        sources: list[SourceConfig],
        period_start: datetime,
        feedback_chat_id: str | None = None,
    ) -> tuple[list[Candidate], list[SourceHealth], list[str]]:
        candidates: list[Candidate] = []
        health: list[SourceHealth] = []
        liked_examples: list[str] = []
        with self.client:
            for source in sources:
                try:
                    items = self._collect_with_retry(source, period_start)
                    candidates.extend(items)
                    health.append(
                        SourceHealth(
                            source_id=source.id,
                            source_name=source.name,
                            status="ok" if items else "empty",
                            candidates=len(items),
                            detail="" if items else "No recent posts",
                        )
                    )
                except FloodWait as exc:
                    health.append(
                        SourceHealth(
                            source_id=source.id,
                            source_name=source.name,
                            status="error",
                            detail=f"FloodWait: retry after {exc.value}s",
                        )
                    )
                except Exception as exc:
                    LOGGER.exception("Telegram source %s failed", source.id)
                    health.append(
                        SourceHealth(
                            source_id=source.id,
                            source_name=source.name,
                            status="error",
                            detail=f"{type(exc).__name__}: {exc}",
                        )
                    )
            if feedback_chat_id:
                try:
                    liked_examples = self._read_liked_examples(feedback_chat_id)
                except Exception as exc:
                    LOGGER.warning("Feedback read failed: %s", exc)
        return candidates, health, liked_examples

    def _collect_with_retry(self, source: SourceConfig, period_start: datetime) -> list[Candidate]:
        try:
            return self._collect_channel(source, period_start)
        except FloodWait as exc:
            if exc.value > 60:
                raise
            LOGGER.warning("FloodWait %ss for %s; retrying once", exc.value, source.id)
            time.sleep(exc.value + 1)
            return self._collect_channel(source, period_start)

    def _collect_channel(self, source: SourceConfig, period_start: datetime) -> list[Candidate]:
        if not source.username:
            raise ValueError(f"Telegram source {source.id} has no username")
        items: list[Candidate] = []
        for message in self.client.get_chat_history(source.username, limit=250):
            published = message.date
            if published.tzinfo is None:
                published = published.replace(tzinfo=period_start.tzinfo)
            if published < period_start:
                break
            text = (message.text or message.caption or "").strip()
            if not text:
                continue
            reaction_total = 0
            if message.reactions:
                reaction_total = _reaction_total(message.reactions)
            items.append(
                Candidate(
                    source_id=source.id,
                    source_name=source.name,
                    source_kind=SourceKind.TELEGRAM,
                    region=source.region,
                    title=text.splitlines()[0][:180],
                    url=f"https://t.me/{source.username}/{message.id}",
                    published_at=published,
                    summary=text[:3000],
                    full_text=text,
                    views=message.views,
                    reactions=reaction_total,
                    extraction_method="telegram",
                )
            )
        return items

    def read_liked_examples(self, chat_id: str, limit: int = 200) -> list[str]:
        with self.client:
            return self._read_liked_examples(chat_id, limit)

    def _read_liked_examples(self, chat_id: str, limit: int = 200) -> list[str]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=120)
        examples: list[str] = []
        for message in self.client.get_chat_history(chat_id, limit=limit):
            published = message.date
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            if published < cutoff:
                break
            reactions = getattr(message.reactions, "reactions", message.reactions or [])
            heart_count = sum(
                int(getattr(item, "count", 0))
                for item in reactions
                if getattr(item, "emoji", "") in {"❤", "❤️"}
            )
            text = (message.text or message.caption or "").strip()
            if heart_count > 0 and text and not text.startswith("📢"):
                examples.append(text[:1500])
        return examples[:10]


def _reaction_total(reactions: object) -> int:
    items = getattr(reactions, "reactions", reactions)
    return sum(int(getattr(item, "count", 0)) for item in items)
