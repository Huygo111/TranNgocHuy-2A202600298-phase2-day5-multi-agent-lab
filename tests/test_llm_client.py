from types import SimpleNamespace

import pytest

from multi_agent_research_lab.core.errors import ValidationError
from multi_agent_research_lab.services import llm_client
from multi_agent_research_lab.services.llm_client import LLMClient


def test_complete_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        llm_client,
        "get_settings",
        lambda: SimpleNamespace(
            openai_api_key=None,
            openai_model="gpt-4o-mini",
            timeout_seconds=60,
        ),
    )

    client = LLMClient()

    with pytest.raises(ValidationError):
        client.complete("system", "user")


def test_complete_returns_usage_and_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        llm_client,
        "get_settings",
        lambda: SimpleNamespace(
            openai_api_key="test-key",
            openai_model="gpt-4o-mini",
            timeout_seconds=60,
        ),
    )

    client = LLMClient()
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="final answer"))],
        usage=SimpleNamespace(prompt_tokens=1000, completion_tokens=500),
    )
    monkeypatch.setattr(client, "_create_completion", lambda system_prompt, user_prompt: response)

    result = client.complete("system", "user")

    assert result.content == "final answer"
    assert result.input_tokens == 1000
    assert result.output_tokens == 500
    assert result.cost_usd == pytest.approx(0.00045)


def test_complete_validates_non_empty_prompts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        llm_client,
        "get_settings",
        lambda: SimpleNamespace(
            openai_api_key="test-key",
            openai_model="gpt-4o-mini",
            timeout_seconds=60,
        ),
    )

    client = LLMClient()

    with pytest.raises(ValidationError):
        client.complete("", "user")

    with pytest.raises(ValidationError):
        client.complete("system", "")
