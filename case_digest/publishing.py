from __future__ import annotations

from datetime import datetime

import requests

from .models import SelectedCase


def render_preview(cases: list[SelectedCase], period_start: datetime, period_end: datetime) -> str:
    lines = [
        "# Case Digest — предварительный просмотр",
        "",
        f"Период: {period_start:%d.%m.%Y} — {period_end:%d.%m.%Y}",
        "",
    ]
    if not cases:
        lines.append("Достойных кейсов не найдено.")
        return "\n".join(lines) + "\n"
    lines.extend(["## Сигналы недели", ""])
    lines.extend(f"- {signal}" for signal in _weekly_signals(cases))
    lines.append("")
    for region, heading in (("ru", "Россия"), ("intl", "Зарубежные рынки")):
        lines.extend([f"## {heading}", ""])
        region_cases = [case for case in cases if case.candidate.region.value == region]
        if not region_cases:
            lines.extend(["Достойных кейсов не найдено.", ""])
            continue
        for case in region_cases:
            a = case.assessment
            lines.extend(
                [
                    f"### {a.brand or case.candidate.title}",
                    "",
                    f"- Рынок: {a.market or case.candidate.region.value}",
                    f"- Тип: {a.activation_type or 'не определён'}",
                    f"- Механика: {a.mechanism}",
                    f"- Почему интересно: {a.why_interesting}",
                    f"- Инсайт: {a.cultural_insight}",
                    f"- Оценка: {a.weighted_score}/10; уверенность: {a.confidence:.0%}",
                    f"- Источник: {case.candidate.url}",
                    "",
                ]
            )
    return "\n".join(lines)


class TelegramPublisher:
    def __init__(self, token: str, chat_id: str):
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"
        self.chat_id = chat_id

    def publish(self, cases: list[SelectedCase], period_start: datetime, period_end: datetime) -> list[int]:
        intro = (
            "📢 <b>Case Digest</b>\n\n"
            f"Период: {period_start:%d.%m.%Y} — {period_end:%d.%m.%Y}\n"
            f"Отобрано кейсов: {len(cases)}\n\n"
            "<b>Сигналы недели:</b>\n"
            + "\n".join(f"• {_escape(signal)}" for signal in _weekly_signals(cases))
        )
        message_ids = [self._send(intro)]
        for case in cases:
            a = case.assessment
            text = (
                f"<b>{_escape(a.brand or case.candidate.title)}</b> · {_escape(a.market)} · {_escape(a.activation_type)}\n\n"
                f"{_escape(a.mechanism)}\n\n"
                f"<b>Почему интересно:</b> {_escape(a.why_interesting)}\n"
                f"<b>Инсайт:</b> {_escape(a.cultural_insight)}\n\n"
                f'<a href="{_escape(case.candidate.url)}">Источник</a>'
            )
            message_ids.append(self._send(text))
        return message_ids

    def _send(self, text: str) -> int:
        response = requests.post(
            self.url,
            json={
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML",
                "link_preview_options": {"is_disabled": True},
            },
            timeout=30,
        )
        response.raise_for_status()
        return int(response.json()["result"]["message_id"])


def _escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _weekly_signals(cases: list[SelectedCase], limit: int = 3) -> list[str]:
    signals: list[str] = []
    for case in cases:
        signal = case.assessment.cultural_insight or case.assessment.why_interesting
        signal = signal.strip()
        if signal and signal not in signals:
            signals.append(signal)
        if len(signals) == limit:
            break
    return signals or ["Недостаточно подтверждённых материалов для вывода о трендах."]
