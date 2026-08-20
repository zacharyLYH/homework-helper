import pytest
from pydantic import ValidationError

from memory.llm import _make_llm
from memory.llm import _make_response_format_schema
from memory.llm import _parse_evaluation


def test_parse_evaluation_skip_only_defaults() -> None:
    evaluation = _parse_evaluation('{"skip": true}')

    assert evaluation.skip is True
    assert evaluation.observations == []
    assert evaluation.concept_upserts == []
    assert evaluation.concept_edges == []
    assert evaluation.concept_state_deltas == []
    assert evaluation.trait_updates == {}
    assert evaluation.updated_summary == ""


def test_parse_evaluation_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        _parse_evaluation('{"skip": false, "extra": "nope"}')


def test_parse_evaluation_rejects_out_of_range_values() -> None:
    with pytest.raises(ValidationError):
        _parse_evaluation(
            '{"concept_edges": [{"from_concept_key": "a", "to_concept_key": "b", "relation": "related", "weight": 1.2}]}'
        )


def test_parse_evaluation_supports_langchain_content_list() -> None:
    content = [
        {"type": "text", "text": '{"trait_updates": {"prefers_visuals": "true"}}'}
    ]
    evaluation = _parse_evaluation(content)

    assert evaluation.trait_updates == {"prefers_visuals": "true"}


def test_response_format_schema_is_strict_json_schema() -> None:
    response_format = _make_response_format_schema()

    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "memory_evaluation"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"]["type"] == "object"


def test_make_llm_adds_openrouter_require_parameters() -> None:
    llm = _make_llm(
        base_url="https://openrouter.ai/api/v1",
        api_key="test-key",
        model="openai/gpt-4o-mini",
    )

    assert llm.model_kwargs["provider"] == {"require_parameters": True}


def test_make_llm_does_not_add_provider_for_non_openrouter() -> None:
    llm = _make_llm(
        base_url="https://api.openai.com/v1",
        api_key="test-key",
        model="gpt-4o-mini",
    )

    assert "provider" not in llm.model_kwargs
