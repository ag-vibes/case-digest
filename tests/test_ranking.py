from case_digest.models import Candidate, CaseAssessment, Region, SelectedCase, SourceKind
from case_digest.ranking import canonical_url, deduplicate, select_cases


def candidate(title: str, url: str, region: Region = Region.RU) -> Candidate:
    return Candidate(
        source_id="source", source_name="Source", source_kind=SourceKind.RSS,
        region=region, title=title, url=url, full_text="x" * 1000
    )


def assessment(url: str, score: float, is_case: bool = True) -> CaseAssessment:
    return CaseAssessment(
        candidate_url=url, is_case=is_case, novelty=score, insight=score, clarity=score,
        execution=score, evidence_quality=score, confidence=0.9
    )


def test_canonical_url_removes_tracking_parameters():
    assert canonical_url("https://EXAMPLE.com/a/?utm_source=x&id=1#top") == "https://example.com/a?id=1"


def test_deduplicate_by_url_and_similar_title():
    items = [
        candidate("Brand launches unusual outdoor campaign", "https://example.com/a?utm_source=x"),
        candidate("Brand launches unusual outdoor campaign!", "https://other.com/story"),
        candidate("Another activation", "https://example.com/a"),
    ]

    result = deduplicate(items)

    assert len(result) == 1


def test_weighted_score_and_selection_do_not_fill_quota():
    strong = candidate("Strong", "https://example.com/strong")
    weak = candidate("Weak", "https://example.com/weak")
    cases = [
        SelectedCase(candidate=strong, assessment=assessment(strong.url, 8)),
        SelectedCase(candidate=weak, assessment=assessment(weak.url, 5)),
    ]

    selected = select_cases(cases)

    assert [item.candidate.title for item in selected] == ["Strong"]
    assert selected[0].assessment.weighted_score == 8

