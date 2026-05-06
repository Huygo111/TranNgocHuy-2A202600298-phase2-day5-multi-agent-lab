import json
from types import SimpleNamespace
from typing import Any

import pytest

from multi_agent_research_lab.core.errors import ValidationError
from multi_agent_research_lab.services import search_client
from multi_agent_research_lab.services.search_client import SearchClient


def test_search_returns_mock_results_without_tavily_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        search_client,
        "get_settings",
        lambda: SimpleNamespace(tavily_api_key=None, timeout_seconds=60),
    )

    client = SearchClient()
    results = client.search("multi-agent systems", max_results=5)

    assert len(results) == 3
    assert results[0].metadata["provider"] == "mock"
    assert "multi-agent systems" in results[0].title


def test_search_validates_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        search_client,
        "get_settings",
        lambda: SimpleNamespace(tavily_api_key=None, timeout_seconds=60),
    )

    client = SearchClient()

    with pytest.raises(ValidationError):
        client.search("")

    with pytest.raises(ValidationError):
        client.search("valid query", max_results=0)


def test_search_uses_tavily_when_key_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        search_client,
        "get_settings",
        lambda: SimpleNamespace(tavily_api_key="test-key", timeout_seconds=60),
    )

    response_payload = {
        "results": [
            {
                "title": "Agent architectures",
                "url": "https://example.com/agent-architectures",
                "content": "Overview of multi-agent architectures.",
            }
        ]
    }

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: Any,
        ) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(response_payload).encode("utf-8")

    captured: dict[str, object] = {}

    def fake_urlopen(request_obj: Any, timeout: int) -> FakeResponse:
        captured["url"] = request_obj.full_url
        captured["timeout"] = timeout
        captured["method"] = request_obj.get_method()
        return FakeResponse()

    monkeypatch.setattr(
        "multi_agent_research_lab.services.search_client.request.urlopen",
        fake_urlopen,
    )

    client = SearchClient()
    results = client.search("agent architecture", max_results=2)

    assert len(results) == 1
    assert results[0].metadata["provider"] == "tavily"
    assert captured["url"] == "https://api.tavily.com/search"
    assert captured["method"] == "POST"
