from pathlib import Path

from case_digest.config import load_sources
from case_digest.models import SourceKind


def test_sources_config_is_valid():
    sources = load_sources(Path("sources.yaml"))

    assert len(sources) == 14
    assert any(item.id == "sostav" and item.kind is SourceKind.RSS for item in sources)
    assert any(item.id == "the_drum" and item.kind is SourceKind.SITEMAP for item in sources)
    assert any(item.id == "marketing_week" and item.kind is SourceKind.GOOGLE_NEWS for item in sources)
    assert all(item.id != "lbbonline" for item in sources)

