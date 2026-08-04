from datetime import datetime, timezone

from case_digest.models import Candidate, CaseAssessment, Region, SelectedCase, SourceKind
from case_digest.publishing import render_preview


def test_preview_contains_separate_case_and_source():
    candidate = Candidate(
        source_id="source", source_name="Source", source_kind=SourceKind.RSS,
        region=Region.RU, title="Campaign", url="https://example.com/case"
    )
    assessment = CaseAssessment(
        candidate_url=candidate.url, is_case=True, brand="Brand", market="Россия",
        activation_type="OOH", mechanism="Механика", why_interesting="Интерес",
        cultural_insight="Инсайт", novelty=8, insight=8, clarity=8, execution=8,
        evidence_quality=8, confidence=0.9
    )

    preview = render_preview(
        [SelectedCase(candidate=candidate, assessment=assessment)],
        datetime(2026, 7, 28, tzinfo=timezone.utc),
        datetime(2026, 8, 4, tzinfo=timezone.utc),
    )

    assert "### Brand" in preview
    assert "Источник: https://example.com/case" in preview
    assert "## Зарубежные рынки\n\nДостойных кейсов не найдено." in preview

