from __future__ import annotations

import logging
from urllib.parse import urlparse

import requests
import trafilatura

from .collectors import USER_AGENT
from .models import Candidate, SourceKind

LOGGER = logging.getLogger(__name__)


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
            LOGGER.info("Direct extraction failed for %s: %s", candidate.url, exc)

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

