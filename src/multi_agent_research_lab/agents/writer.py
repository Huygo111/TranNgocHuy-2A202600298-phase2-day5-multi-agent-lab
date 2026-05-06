"""Writer agent skeleton."""

from typing import Protocol

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.errors import ValidationError
from multi_agent_research_lab.core.schemas import AgentName, AgentResult
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.services.llm_client import LLMClient, LLMResponse


class SupportsCompletion(Protocol):
    def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse: ...


class WriterAgent(BaseAgent):
    """Produces final answer from research and analysis notes."""

    name = "writer"

    def __init__(self, llm_client: SupportsCompletion | None = None) -> None:
        self._llm_client = llm_client or LLMClient()

    def run(self, state: ResearchState) -> ResearchState:
        """Populate `state.final_answer`.

        Synthesize a final answer with source references.
        """

        if not state.research_notes:
            raise ValidationError("research_notes are required before running WriterAgent")
        if not state.analysis_notes:
            raise ValidationError("analysis_notes are required before running WriterAgent")

        source_references = "\n".join(
            f"- {source.title} ({source.url or 'no-url'})"
            for source in state.sources
        )
        response = self._llm_client.complete(
            system_prompt=(
                "You are a writer. Produce a clear, polished final answer for technical "
                "learners. Use the analysis notes, keep claims grounded in the sources, and "
                "reference sources inline when possible."
            ),
            user_prompt=(
                f"Query: {state.request.query}\n"
                f"Audience: {state.request.audience}\n"
                f"Research notes:\n{state.research_notes}\n\n"
                f"Analysis notes:\n{state.analysis_notes}\n\n"
                f"Sources:\n{source_references}"
            ),
        )

        state.final_answer = response.content
        state.agent_results.append(
            AgentResult(
                agent=AgentName.WRITER,
                content=response.content,
                metadata={
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                    "cost_usd": response.cost_usd,
                    "source_count": len(state.sources),
                },
            )
        )
        state.add_trace_event(
            "writer_completed",
            {
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "cost_usd": response.cost_usd,
                "source_count": len(state.sources),
            },
        )
        return state
