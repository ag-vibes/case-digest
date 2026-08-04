from __future__ import annotations

import re
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import Candidate, SelectedCase

CASE_TERMS = {
    "campaign",
    "кампания",
    "brand",
    "бренд",
    "activation",
    "активац",
    "collab",
    "коллаб",
    "creative",
    "креатив",
    "outdoor",
    "ooh",
    "dooh",
    "experiential",
    "pop-up",
    "launch",
    "запустил",
    "реклама",
}
EXCLUSION_TERMS = {
    "ваканси",
    "назначен",
    "уволен",
    "отчет",
    "отчёт",
    "финансовые результаты",
    "скидка",
    "промокод",
    "performance marketing",
}
TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "gclid", "fbclid"}


def discovery_score(candidate: Candidate) -> float:
    text = f"{candidate.title} {candidate.summary} {candidate.full_text[:3000]}".lower()
    positive = sum(1 for term in CASE_TERMS if term in text)
    negative = sum(1 for term in EXCLUSION_TERMS if term in text)
    evidence = 1 if len(candidate.full_text) >= 800 else 0
    telegram_signal = 0.0
    if candidate.views and candidate.reactions is not None and candidate.views > 0:
        telegram_signal = min((candidate.reactions / candidate.views) * 50, 1.5)
    return round(positive + evidence + telegram_signal - negative * 2, 3)


def canonical_url(url: str) -> str:
    parts = urlsplit(url)
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if k.lower() not in TRACKING_PARAMS])
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), query, ""))


def deduplicate(candidates: list[Candidate], title_threshold: float = 0.88) -> list[Candidate]:
    ranked = sorted(candidates, key=lambda item: (len(item.full_text), item.discovery_score), reverse=True)
    kept: list[Candidate] = []
    urls: set[str] = set()
    titles: list[str] = []
    for candidate in ranked:
        url = canonical_url(candidate.url)
        title = _normalise_title(candidate.title)
        if url in urls:
            continue
        if title and any(SequenceMatcher(None, title, other).ratio() >= title_threshold for other in titles):
            continue
        urls.add(url)
        titles.append(title)
        kept.append(candidate)
    return kept


def select_cases(cases: list[SelectedCase], limit_per_region: int = 5, threshold: float = 6.5) -> list[SelectedCase]:
    selected: list[SelectedCase] = []
    for region in ("ru", "intl"):
        region_cases = [
            case
            for case in cases
            if case.candidate.region.value == region
            and case.assessment.is_case
            and case.assessment.weighted_score >= threshold
            and case.assessment.confidence >= 0.55
        ]
        region_cases.sort(key=lambda case: case.assessment.weighted_score, reverse=True)
        selected.extend(region_cases[:limit_per_region])
    return selected


def _normalise_title(value: str) -> str:
    return re.sub(r"[^a-zа-я0-9]+", " ", value.lower()).strip()

