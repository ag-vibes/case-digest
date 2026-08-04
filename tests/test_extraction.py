from case_digest.extraction import _source_domain


def test_source_domain_normalises_www():
    assert _source_domain("https://www.thedrum.com/sitemap.xml") == "thedrum.com"
    assert _source_domain("https://famouscampaigns.substack.com/feed") == "famouscampaigns.substack.com"
