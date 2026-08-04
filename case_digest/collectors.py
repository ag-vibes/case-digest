from __future__ import annotations

import gzip
import logging
import re
import xml.etree.ElementTree as ET
from calendar import timegm
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import quote_plus

import feedparser
import requests

from .models import Candidate, SourceConfig, SourceHealth, SourceKind

LOGGER = logging.getLogger(__name__)
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 CaseDigest/0.1"
)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _entry_date(entry: feedparser.FeedParserDict) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime.fromtimestamp(timegm(parsed), tz=timezone.utc)
    for key in ("published", "updated"):
        value = entry.get(key)
        if not value:
            continue
        try:
            return _as_utc(parsedate_to_datetime(value))
        except (TypeError, ValueError):
            try:
                return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
            except ValueError:
                pass
    return None


def _clean_html(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", value))).strip()


class WebCollector:
    def __init__(self, session: requests.Session | None = None, timeout: int = 30):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.timeout = timeout

    def collect(
        self, source: SourceConfig, period_start: datetime
    ) -> tuple[list[Candidate], SourceHealth]:
        try:
            if source.kind in {SourceKind.RSS, SourceKind.GOOGLE_NEWS}:
                items = self._collect_feed(source, period_start)
            elif source.kind is SourceKind.SITEMAP:
                items = self._collect_sitemap(source, period_start)
            else:
                raise ValueError(f"Unsupported web source kind: {source.kind}")
            return items, SourceHealth(
                source_id=source.id,
                source_name=source.name,
                status="ok" if items else "empty",
                candidates=len(items),
                detail="" if items else "No recent candidates",
            )
        except Exception as exc:
            LOGGER.exception("Source %s failed", source.id)
            return [], SourceHealth(
                source_id=source.id,
                source_name=source.name,
                status="error",
                detail=f"{type(exc).__name__}: {exc}",
            )

    def _collect_feed(self, source: SourceConfig, period_start: datetime) -> list[Candidate]:
        url = source.url
        if source.kind is SourceKind.GOOGLE_NEWS:
            url = f"https://news.google.com/rss/search?q={quote_plus(source.query or '')}&hl=en&gl=US&ceid=US:en"
        if not url:
            raise ValueError(f"Source {source.id} has no URL")
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        if feed.bozo and not feed.entries:
            raise ValueError(f"Invalid feed: {feed.bozo_exception}")
        candidates: list[Candidate] = []
        for entry in feed.entries:
            published = _entry_date(entry)
            if published and published < period_start:
                continue
            link = str(entry.get("link", "")).strip()
            title = _clean_html(str(entry.get("title", "")))
            if not title or not link:
                continue
            candidates.append(
                Candidate(
                    source_id=source.id,
                    source_name=source.name,
                    source_kind=source.kind,
                    region=source.region,
                    title=title,
                    url=link,
                    published_at=published,
                    summary=_clean_html(str(entry.get("summary", "")))[:2000],
                )
            )
        return candidates

    def _collect_sitemap(self, source: SourceConfig, period_start: datetime) -> list[Candidate]:
        if not source.url:
            raise ValueError(f"Source {source.id} has no URL")
        return self._walk_sitemap(source, source.url, period_start, depth=0)

    def _walk_sitemap(
        self, source: SourceConfig, url: str, period_start: datetime, depth: int
    ) -> list[Candidate]:
        if depth > 2:
            return []
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        payload = response.content
        if url.endswith(".gz") and payload.startswith(b"\x1f\x8b"):
            payload = gzip.decompress(payload)
        root = ET.fromstring(payload)
        namespace = ""
        if root.tag.startswith("{"):
            namespace = root.tag.split("}", 1)[0] + "}"
        if root.tag.endswith("sitemapindex"):
            results: list[Candidate] = []
            children = root.findall(f"{namespace}sitemap")
            for child in children:
                loc = child.findtext(f"{namespace}loc", "").strip()
                lastmod = _parse_iso_date(child.findtext(f"{namespace}lastmod", ""))
                if not loc or (lastmod and lastmod < period_start):
                    continue
                if not lastmod and not _archive_overlaps_period(loc, period_start):
                    continue
                results.extend(self._walk_sitemap(source, loc, period_start, depth + 1))
            return results
        results = []
        for node in root.findall(f"{namespace}url"):
            loc = node.findtext(f"{namespace}loc", "").strip()
            lastmod = _parse_iso_date(node.findtext(f"{namespace}lastmod", ""))
            if not loc or (lastmod and lastmod < period_start):
                continue
            if source.include_pattern and source.include_pattern not in loc:
                continue
            results.append(
                Candidate(
                    source_id=source.id,
                    source_name=source.name,
                    source_kind=source.kind,
                    region=source.region,
                    title=_title_from_url(loc),
                    url=loc,
                    published_at=lastmod,
                )
            )
        return results


def _parse_iso_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _title_from_url(url: str) -> str:
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"[-_]", " ", slug).strip().title()


def _archive_overlaps_period(url: str, period_start: datetime) -> bool:
    years = {int(value) for value in re.findall(r"(?<!\d)(20\d{2})(?!\d)", url)}
    if not years:
        return True
    period_end_year = (period_start + timedelta(days=8)).year
    return bool(years & {period_start.year, period_end_year})
