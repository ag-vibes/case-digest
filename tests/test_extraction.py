from datetime import timezone

from case_digest.extraction import _parse_tavily_date, _source_domain


def test_source_domain_normalises_www():
    assert _source_domain("https://www.thedrum.com/sitemap.xml") == "thedrum.com"
    assert _source_domain("https://famouscampaigns.substack.com/feed") == "famouscampaigns.substack.com"


def test_tavily_date_must_be_explicit_and_valid():
    parsed = _parse_tavily_date("2026-08-04T12:00:00Z")

    assert parsed is not None
    assert parsed.tzinfo == timezone.utc
    assert _parse_tavily_date("Tue, 04 Aug 2026 12:00:00 GMT") is not None
    assert _parse_tavily_date(None) is None
    assert _parse_tavily_date("unknown") is None
