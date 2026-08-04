from __future__ import annotations

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import requests
import trafilatura

from .collectors import USER_AGENT
from .models import Candidate, SourceConfig, SourceKind

LOGGER = logging.getLogger(__name__)


def discover_with_tavily(
    source: SourceConfig, api_key: str, period_start: datetime
) -> list[Candidate]:
    domain = source.allowed_domain or _source_domain(source.url or "")
    if not domain:
        return []
    response = requests.post(
        "https://api.tavily.com/search",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "query": (
                f"site:{domain} advertising marketing campaign case "
                f"after:{period_start.date().isoformat()}"
            ),
            "include_domains": [domain],
            "search_depth": "basic",
            "topic": "news",
            "days": 8,
            "max_results": 20,
            "include_raw_content": "text",
        },
        timeout=60,
    )
    response.raise_for_status()
    candidates: list[Candidate] = []
    for result in response.json().get("results", []):
        url = str(result.get("url", "")).strip()
        title = str(result.get("title", "")).strip()
        published_at = _parse_tavily_date(result.get("published_date"))
        if (
            not url
            or not title
            or not _source_domain(url).endswith(domain)
            or published_at is None
            or published_at < period_start
        ):
            continue
        raw_content = result.get("raw_content") or ""
        candidates.append(
            Candidate(
                source_id=source.id,
                source_name=source.name,
                source_kind=source.kind,
                region=source.region,
                title=title,
                url=url,
                published_at=published_at,
                summary=str(result.get("content", ""))[:2000],
                full_text=str(raw_content)[:20000] if raw_content else "",
                extraction_method="tavily_discovery" if raw_content else None,
            )
        )
    return candidates


def _source_domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _parse_tavily_date(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value.strip())
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class ContentExtractor:
    def __init__(self, tavily_api_key: str | None, timeout: int = 30):
        self.tavily_api_key = tavily_api_key
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def enrich(self, candidate: Candidate) -> Candidate:
        if candidate.full_text:
            return candidate
        resolved_url = candidate.url
        try:
            response = self.session.get(candidate.url, timeout=self.timeout, allow_redirects=True)
            response.raise_for_status()
            resolved_url = response.url
            text = trafilatura.extract(
                response.text,
                include_comments=False,
                include_tables=False,
                favor_precision=True,
            )
            if text and len(text) >= 500:
                candidate.url = resolved_url
                candidate.full_text = text[:20000]
                candidate.extraction_method = "direct"
                return candidate
        except requests.RequestException as exc:
            LOGGER.debug("Direct extraction failed for %s: %s", candidate.url, exc)

        if self.tavily_api_key:
            tavily_result = self._tavily_extract(resolved_url)
            if not tavily_result and candidate.source_kind is SourceKind.GOOGLE_NEWS:
                tavily_result = self._tavily_search(candidate)
            if tavily_result:
                candidate.url, candidate.full_text = tavily_result
                candidate.extraction_method = "tavily"
        return candidate

    def _tavily_extract(self, url: str) -> tuple[str, str] | None:
        try:
            response = self.session.post(
                "https://api.tavily.com/extract",
                headers={"Authorization": f"Bearer {self.tavily_api_key}"},
                json={"urls": [url], "extract_depth": "basic", "format": "text"},
                timeout=60,
            )
            response.raise_for_status()
            results = response.json().get("results", [])
            if results and len(results[0].get("raw_content", "")) >= 300:
                return results[0].get("url", url), results[0]["raw_content"][:20000]
        except requests.RequestException as exc:
            LOGGER.info("Tavily extraction failed for %s: %s", url, exc)
        return None

    def _tavily_search(self, candidate: Candidate) -> tuple[str, str] | None:
        try:
            response = self.session.post(
                "https://api.tavily.com/search",
                headers={"Authorization": f"Bearer {self.tavily_api_key}"},
                json={
                    "query": candidate.title,
                    "include_domains": ["marketingweek.com"],
                    "search_depth": "basic",
                    "max_results": 3,
                    "include_raw_content": "text",
                },
                timeout=60,
            )
            response.raise_for_status()
            for result in response.json().get("results", []):
                content = result.get("raw_content") or result.get("content") or ""
                if len(content) >= 300 and urlparse(result.get("url", "")).netloc.endswith("marketingweek.com"):
                    return result["url"], content[:20000]
        except requests.RequestException as exc:
            LOGGER.info("Tavily search failed for %s: %s", candidate.title, exc)
        return None
