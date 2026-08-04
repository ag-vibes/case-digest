from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .collectors import WebCollector
from .config import Settings, load_sources
from .extraction import ContentExtractor
from .llm import OpenRouterAssessor
from .models import Candidate, RunReport, SourceHealth, SourceKind
from .publishing import render_preview
from .ranking import deduplicate, discovery_score, select_cases
from .telegram_reader import TelegramReader

LOGGER = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, settings: Settings, source_path: Path, artifacts_dir: Path):
        self.settings = settings
        self.sources = load_sources(source_path)
        self.artifacts_dir = artifacts_dir

    def run(self, include_telegram: bool = True, days: int = 7) -> RunReport:
        started_at = datetime.now(timezone.utc)
        period_end = started_at
        period_start = period_end - timedelta(days=days)
        candidates, source_health, liked_examples = self._collect(period_start, include_telegram)
        if not candidates:
            raise RuntimeError("Сбор завершился без единого кандидата; запуск нельзя считать успешным")

        for candidate in candidates:
            candidate.discovery_score = discovery_score(candidate)
        candidates = self._cap_by_source(candidates, 25)
        candidates = self._extract(candidates, self.settings.tavily_api_key)
        for candidate in candidates:
            candidate.discovery_score = discovery_score(candidate)

        extracted_count = sum(bool(item.full_text) for item in candidates)
        unique = deduplicate(candidates)
        shortlist = self._shortlist(unique, 24)
        if not self.settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY нужен для содержательной оценки dry-run")
        assessed = OpenRouterAssessor(
            self.settings.openrouter_api_key, self.settings.openrouter_model
        ).assess(shortlist, liked_examples)
        selected = select_cases(assessed)
        rejected = [
            {
                "url": item.candidate.url,
                "title": item.candidate.title,
                "score": item.assessment.weighted_score,
                "confidence": item.assessment.confidence,
                "reason": item.assessment.exclusion_reason
                or ("score below threshold" if item.assessment.is_case else "not a complete case"),
            }
            for item in assessed
            if item not in selected
        ]
        report = RunReport(
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            period_start=period_start,
            period_end=period_end,
            source_health=source_health,
            collected_count=len(candidates),
            extracted_count=extracted_count,
            deduplicated_count=len(unique),
            assessed_count=len(assessed),
            feedback_examples_count=len(liked_examples),
            selected=selected,
            rejected=rejected,
        )
        self._write_artifacts(report)
        return report

    def _collect(
        self, period_start: datetime, include_telegram: bool
    ) -> tuple[list[Candidate], list[SourceHealth], list[str]]:
        web_sources = [source for source in self.sources if source.kind is not SourceKind.TELEGRAM]
        candidates: list[Candidate] = []
        health: list[SourceHealth] = []
        liked_examples: list[str] = []
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {executor.submit(WebCollector().collect, source, period_start): source for source in web_sources}
            for future in as_completed(futures):
                items, status = future.result()
                candidates.extend(items)
                health.append(status)

        if include_telegram:
            telegram_sources = [source for source in self.sources if source.kind is SourceKind.TELEGRAM]
            if not (self.settings.api_id and self.settings.api_hash and self.settings.session_string):
                raise RuntimeError("Для Telegram-сбора нужны API_ID, API_HASH и SESSION_STRING")
            reader = TelegramReader(
                self.settings.api_id, self.settings.api_hash, self.settings.session_string
            )
            telegram_items, telegram_health, liked_examples = reader.collect(
                telegram_sources, period_start, self.settings.telegram_chat_id
            )
            candidates.extend(telegram_items)
            health.extend(telegram_health)

        errors = [item for item in health if item.status == "error"]
        if len(errors) == len(health):
            raise RuntimeError("Все источники завершились ошибкой")
        return candidates, sorted(health, key=lambda item: item.source_id), liked_examples

    @staticmethod
    def _cap_by_source(candidates: list[Candidate], limit: int) -> list[Candidate]:
        grouped: dict[str, list[Candidate]] = {}
        for candidate in candidates:
            grouped.setdefault(candidate.source_id, []).append(candidate)
        output: list[Candidate] = []
        for items in grouped.values():
            items.sort(
                key=lambda item: (
                    item.discovery_score,
                    item.published_at or datetime.min.replace(tzinfo=timezone.utc),
                ),
                reverse=True,
            )
            output.extend(items[:limit])
        return output

    @staticmethod
    def _extract(candidates: list[Candidate], tavily_api_key: str | None) -> list[Candidate]:
        def extract(candidate: Candidate) -> Candidate:
            return ContentExtractor(tavily_api_key).enrich(candidate)

        with ThreadPoolExecutor(max_workers=8) as executor:
            return list(executor.map(extract, candidates))

    @staticmethod
    def _shortlist(candidates: list[Candidate], per_region: int) -> list[Candidate]:
        output: list[Candidate] = []
        for region in ("ru", "intl"):
            items = [
                item
                for item in candidates
                if item.region.value == region
                and item.discovery_score > 0
                and len(item.full_text) >= 300
            ]
            items.sort(key=lambda item: item.discovery_score, reverse=True)
            output.extend(items[:per_region])
        return output

    def _write_artifacts(self, report: RunReport) -> None:
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        preview = render_preview(report.selected, report.period_start, report.period_end)
        (self.artifacts_dir / "preview.md").write_text(preview, encoding="utf-8")
        safe_report = report.model_dump(mode="json")
        for item in safe_report["selected"]:
            item["candidate"]["full_text"] = ""
        (self.artifacts_dir / "report.json").write_text(
            json.dumps(safe_report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
