from datetime import datetime, timezone

from case_digest.collectors import WebCollector, _archive_overlaps_period
from case_digest.models import Region, SourceConfig, SourceKind


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self, payloads: dict[str, bytes]):
        self.payloads = payloads
        self.headers = {}

    def get(self, url, timeout):
        return FakeResponse(self.payloads[url])


def test_rss_collects_recent_and_ignores_old():
    url = "https://example.test/feed"
    payload = b"""<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>Recent campaign</title><link>https://example.test/recent</link>
      <pubDate>Sun, 03 Aug 2026 10:00:00 +0000</pubDate><description>Brand activation</description></item>
      <item><title>Old campaign</title><link>https://example.test/old</link>
      <pubDate>Mon, 20 Jul 2026 10:00:00 +0000</pubDate></item>
    </channel></rss>"""
    source = SourceConfig(id="test", name="Test", region=Region.INTL, kind=SourceKind.RSS, url=url)

    items, health = WebCollector(FakeSession({url: payload})).collect(
        source, datetime(2026, 7, 28, tzinfo=timezone.utc)
    )

    assert [item.title for item in items] == ["Recent campaign"]
    assert health.status == "ok"


def test_sitemap_respects_lastmod_and_pattern():
    url = "https://example.test/sitemap.xml"
    payload = b"""<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.test/news/new-case</loc><lastmod>2026-08-02</lastmod></url>
      <url><loc>https://example.test/about</loc><lastmod>2026-08-02</lastmod></url>
      <url><loc>https://example.test/news/old-case</loc><lastmod>2026-07-01</lastmod></url>
    </urlset>"""
    source = SourceConfig(
        id="test", name="Test", region=Region.INTL, kind=SourceKind.SITEMAP,
        url=url, include_pattern="/news/"
    )

    items, _ = WebCollector(FakeSession({url: payload})).collect(
        source, datetime(2026, 7, 28, tzinfo=timezone.utc)
    )

    assert [item.url for item in items] == ["https://example.test/news/new-case"]


def test_gz_sitemap_may_already_be_decompressed_by_http_client():
    url = "https://example.test/articles.xml.gz"
    payload = b"""<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.test/news/case</loc><lastmod>2026-08-02</lastmod></url>
    </urlset>"""
    source = SourceConfig(
        id="test", name="Test", region=Region.INTL, kind=SourceKind.SITEMAP,
        url=url, include_pattern="/news/"
    )

    items, health = WebCollector(FakeSession({url: payload})).collect(
        source, datetime(2026, 7, 28, tzinfo=timezone.utc)
    )

    assert health.status == "ok"
    assert len(items) == 1


def test_old_yearly_sitemap_is_skipped():
    start = datetime(2026, 7, 28, tzinfo=timezone.utc)

    assert _archive_overlaps_period("https://example.test/articles-2026.xml.gz", start)
    assert not _archive_overlaps_period("https://example.test/articles-2024.xml.gz", start)
