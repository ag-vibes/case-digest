import pytest

from case_digest.llm import _assessment_schema, _find_assessment_items, _parse_json_content


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
