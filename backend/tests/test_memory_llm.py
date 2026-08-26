import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from memory.llm import (
    _make_llm,
    _make_response_format_schema,
    _parse_evaluation,
    evaluate_memory,
)
from memory.schemas import MemoryEvaluationInput


def test_parse_evaluation_accepts_valid_edges_and_state() -> None:
    result = _parse_evaluation(
        json.dumps(
            {
                "skip": False,
                "observations": ["Needs practice"],
                "concept_upserts": [
                    {"concept_key": "fractions", "display_name": "Fractions"}
                ],
                "concept_edges": [
                    {
                        "from_concept_key": "addition",
                        "to_concept_key": "fractions",
                        "relation": "prerequisite",
                        "weight": 0.5,
                    }
                ],
                "concept_state_deltas": [
                    {"concept_key": "fractions", "mastery": 0.25, "confidence": 0.8}
                ],
                "trait_updates": {"pace": "careful"},
                "updated_summary": "Practice fractions.",
            }
        )
    )

    assert result.skip is False
    assert result.concept_edges[0].weight == 0.5
    assert result.concept_state_deltas[0].mastery == 0.25


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("edge", {"relation": "depends", "weight": 0.5}, "Invalid relation"),
        ("edge", {"relation": "related", "weight": 1.1}, "Edge weight out of range"),
        ("state", {"mastery": -0.1, "confidence": 0.5}, "Mastery out of range"),
        ("state", {"mastery": 0.5, "confidence": 1.1}, "Confidence out of range"),
    ],
)
def test_parse_evaluation_rejects_invalid_ranges(field, value, message) -> None:
    data = {"concept_edges": [], "concept_state_deltas": []}
    if field == "edge":
        data["concept_edges"] = [
            {"from_concept_key": "a", "to_concept_key": "b", **value}
        ]
    else:
        data["concept_state_deltas"] = [{"concept_key": "a", **value}]

    with pytest.raises(ValueError):
        _parse_evaluation(json.dumps(data))


def test_make_llm_sets_json_response_configuration() -> None:
    with patch("memory.llm.ChatOpenAI") as chat_openai:
        _make_llm(base_url="https://example.test", api_key="key", model="model")

    kwargs = chat_openai.call_args.kwargs
    assert kwargs["base_url"] == "https://example.test"
    assert kwargs["model"] == "model"
    assert kwargs["temperature"] == 0.0
    response_format = kwargs["model_kwargs"]["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True


def test_evaluate_memory_uses_default_llm_and_parses_response(monkeypatch) -> None:
    state = MemoryEvaluationInput(
        user_id=1,
        subject_id=2,
        turn_snippet=[],
        current_summary="",
        current_traits={},
        current_weak_concepts=[],
    )
    ainvoke = AsyncMock(
        return_value=type("Response", (), {"content": '{"skip": true}'})()
    )
    fake_llm = type("FakeLLM", (), {"ainvoke": ainvoke})()
    monkeypatch.setattr("memory.llm._resolve_memory_llm", lambda _user_id: None)
    monkeypatch.setattr("memory.llm._make_llm", lambda **_kwargs: fake_llm)
    monkeypatch.setattr("memory.llm.MEMORY_LLM_TIMEOUT_SECONDS", 1)

    result = asyncio.run(evaluate_memory(current_state=state))

    assert result.skip is True
    ainvoke.assert_awaited_once()


from pydantic import ValidationError


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


@pytest.mark.parametrize(
    "content",
    [
        "[]",
        '"result"',
        [],
        [{"type": "image", "url": "image"}],
        42,
        None,
    ],
)
def test_parse_evaluation_rejects_unsupported_response_content(content) -> None:
    with pytest.raises((TypeError, ValueError, json.JSONDecodeError)):
        _parse_evaluation(content)


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
