"""Search client abstraction for ResearcherAgent."""

from __future__ import annotations

import json
from urllib import error, request

from multi_agent_research_lab.core.config import get_settings
from multi_agent_research_lab.core.errors import AgentExecutionError, ValidationError
from multi_agent_research_lab.core.schemas import SourceDocument


class SearchClient:
    """Provider-agnostic search client with Tavily support and local fallback."""

    def __init__(self) -> None:
        settings = get_settings()
        self._tavily_api_key = settings.tavily_api_key
        self._timeout_seconds = settings.timeout_seconds

    @staticmethod
    def _build_mock_results(query: str, max_results: int) -> list[SourceDocument]:
        limited_results = min(max_results, 3)
        return [
            SourceDocument(
                title=f"Mock source {index + 1} for: {query}",
                url=f"https://example.com/search/{index + 1}",
                snippet=(
                    f"Mock search result {index + 1} summarizing relevant information "
                    f"about {query}."
                ),
                metadata={"provider": "mock", "rank": index + 1},
            )
            for index in range(limited_results)
        ]

    def _search_tavily(self, query: str, max_results: int) -> list[SourceDocument]:
        payload = json.dumps(
            {
                "api_key": self._tavily_api_key,
                "query": query,
                "max_results": max_results,
                "search_depth": "basic",
            }
        ).encode("utf-8")
        http_request = request.Request(
            url="https://api.tavily.com/search",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(http_request, timeout=self._timeout_seconds) as response:
                response_data = json.loads(response.read().decode("utf-8"))
        except error.URLError as exc:
            raise AgentExecutionError(f"Search request failed: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise AgentExecutionError("Search provider returned invalid JSON") from exc

        results = response_data.get("results")
        if not isinstance(results, list):
            raise AgentExecutionError(
                "Search provider response did not contain a valid results list."
            )

        documents: list[SourceDocument] = []
        for index, item in enumerate(results[:max_results]):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            snippet = str(item.get("content", "")).strip()
            if not title or not snippet:
                continue
            documents.append(
                SourceDocument(
                    title=title,
                    url=str(item.get("url", "")).strip() or None,
                    snippet=snippet,
                    metadata={"provider": "tavily", "rank": index + 1},
                )
            )

        if not documents:
            raise AgentExecutionError("Search provider returned no usable results")
        return documents

    def search(self, query: str, max_results: int = 5) -> list[SourceDocument]:
        """Search for documents relevant to a query.

        Use Tavily when configured; otherwise fall back to deterministic local mock results.
        """

        normalized_query = query.strip()
        if not normalized_query:
            raise ValidationError("query must not be empty")
        if max_results < 1:
            raise ValidationError("max_results must be at least 1")

        if self._tavily_api_key:
            return self._search_tavily(normalized_query, max_results)
        return self._build_mock_results(normalized_query, max_results)
