"""Researcher agent skeleton."""

from typing import Protocol

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.schemas import AgentName, AgentResult, SourceDocument
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.services.llm_client import LLMClient, LLMResponse
from multi_agent_research_lab.services.search_client import SearchClient


class SupportsSearch(Protocol):
    def search(self, query: str, max_results: int = 5) -> list[SourceDocument]: ...


class SupportsCompletion(Protocol):
    def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse: ...


class ResearcherAgent(BaseAgent):
    """Collects sources and creates concise research notes."""

    name = "researcher"

    def __init__(
        self,
        search_client: SupportsSearch | None = None,
        llm_client: SupportsCompletion | None = None,
    ) -> None:
        self._search_client = search_client or SearchClient()
        self._llm_client = llm_client or LLMClient()

    def run(self, state: ResearchState) -> ResearchState:
        """Populate `state.sources` and `state.research_notes`.

        Search for sources and synthesize concise research notes.
        """

        sources = self._search_client.search(
            query=state.request.query,
            max_results=state.request.max_sources,
        )
        formatted_sources = "\n".join(
            f"{index + 1}. {source.title}: {source.snippet}"
            for index, source in enumerate(sources)
        )
        response = self._llm_client.complete(
            system_prompt=(
                "You are a research assistant. Summarize the retrieved sources into concise "
                "research notes for a downstream analyst. Preserve important factual details "
                "and mention where evidence seems thin."
            ),
            user_prompt=(
                f"Query: {state.request.query}\n"
                f"Audience: {state.request.audience}\n"
                f"Sources:\n{formatted_sources}"
            ),
        )

        state.sources = sources
        state.research_notes = response.content
        state.agent_results.append(
            AgentResult(
                agent=AgentName.RESEARCHER,
                content=response.content,
                metadata={
                    "source_count": len(sources),
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                    "cost_usd": response.cost_usd,
                },
            )
        )
        state.add_trace_event(
            "researcher_completed",
            {
                "source_count": len(sources),
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "cost_usd": response.cost_usd,
            },
        )
        return state
