from case_digest.llm import _assessment_schema, _parse_json_content


def test_assessment_schema_requires_all_fields_and_forbids_extra():
    schema = _assessment_schema()
    item = schema["properties"]["assessments"]["items"]

    assert item["additionalProperties"] is False
    assert set(item["required"]) == set(item["properties"])


def test_json_parser_accepts_markdown_fence_fallback():
    parsed = _parse_json_content('```json\n{"assessments": []}\n```')

    assert parsed == {"assessments": []}
