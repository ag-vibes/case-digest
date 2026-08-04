import pytest

from case_digest.llm import (
    _assessment_schema,
    _coerce_metric,
    _find_assessment_items,
    _normalise_assessment_item,
    _parse_json_content,
)
from case_digest.models import CaseAssessment


def test_assessment_schema_requires_all_fields_and_forbids_extra():
    schema = _assessment_schema()
    item = schema["properties"]["assessments"]["items"]

    assert item["additionalProperties"] is False
    assert set(item["required"]) == set(item["properties"])


def test_json_parser_accepts_markdown_fence_fallback():
    parsed = _parse_json_content('```json\n{"assessments": []}\n```')

    assert parsed == {"assessments": []}


@pytest.mark.parametrize(
    "payload",
    [
        {"assessments": [{"candidate_url": "https://example.com"}]},
        {"case_assessments": [{"candidate_url": "https://example.com"}]},
        {"case_assessments": {"results": [{"candidate_url": "https://example.com"}]}},
        [{"candidate_url": "https://example.com"}],
    ],
)
def test_finds_assessment_list_in_common_model_wrappers(payload):
    assert _find_assessment_items(payload) == [{"candidate_url": "https://example.com"}]


def test_missing_assessments_has_clear_error():
    with pytest.raises(ValueError, match="top-level keys: answer"):
        _find_assessment_items({"answer": "not structured"})


def test_partial_rejection_is_safe_and_scores_zero():
    assessment = CaseAssessment.model_validate(
        {
            "candidate_url": "https://example.com/not-a-case",
            "exclusion_reason": "Материал не описывает полноценный кейс",
        }
    )

    assert assessment.is_case is False
    assert assessment.weighted_score == 0
    assert assessment.confidence == 0


def test_cases_and_excluded_are_merged_and_normalised():
    payload = {
        "cases": [
            {
                "url": "https://example.com/case",
                "scores": {
                    "novelty": 8,
                    "insight": 7,
                    "clarity": 6,
                    "execution": 9,
                    "evidence_quality": 8,
                },
                "confidence": 0.9,
            }
        ],
        "excluded": [
            {"url": "https://example.com/news", "reason": "Не полноценный кейс"}
        ],
    }

    items = [_normalise_assessment_item(item) for item in _find_assessment_items(payload)]

    assert items[0]["candidate_url"] == "https://example.com/case"
    assert items[0]["is_case"] is True
    assert items[0]["novelty"] == 8
    assert items[1]["is_case"] is False
    assert items[1]["exclusion_reason"] == "Не полноценный кейс"


@pytest.mark.parametrize(
    ("value", "maximum", "expected"),
    [(95, 1, 0.95), ("80%", 10, 8), ("7.5/10", 10, 7.5), (120, 10, 10)],
)
def test_metric_coercion_handles_percentages(value, maximum, expected):
    assert _coerce_metric(value, maximum) == expected
