import pytest

from multi_agent_research_lab.agents.analyst import AnalystAgent
from multi_agent_research_lab.agents.critic import CriticAgent
from multi_agent_research_lab.agents.researcher import ResearcherAgent
from multi_agent_research_lab.agents.writer import WriterAgent
from multi_agent_research_lab.core.errors import ValidationError
from multi_agent_research_lab.core.schemas import ResearchQuery, SourceDocument
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.services.llm_client import LLMResponse


class FakeLLMClient:
    def __init__(self, content: str) -> None:
        self._content = content

    def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        assert system_prompt
        assert user_prompt
        return LLMResponse(
            content=self._content,
            input_tokens=10,
            output_tokens=20,
            cost_usd=0.001,
        )


class FakeSearchClient:
    def search(self, query: str, max_results: int = 5) -> list[SourceDocument]:
        assert query
        assert max_results == 5
        return [
            SourceDocument(
                title="Source A",
                url="https://example.com/a",
                snippet="Snippet A",
            ),
            SourceDocument(
                title="Source B",
                url="https://example.com/b",
                snippet="Snippet B",
            ),
        ]


def test_researcher_agent_populates_sources_and_notes() -> None:
    state = ResearchState(request=ResearchQuery(query="Explain multi-agent systems"))
    agent = ResearcherAgent(
        search_client=FakeSearchClient(),
        llm_client=FakeLLMClient("research notes"),
    )

    result = agent.run(state)

    assert len(result.sources) == 2
    assert result.research_notes == "research notes"
    assert result.agent_results[-1].agent == "researcher"
    assert result.trace[-1]["name"] == "researcher_completed"


def test_analyst_agent_requires_research_notes() -> None:
    state = ResearchState(request=ResearchQuery(query="Explain multi-agent systems"))
    agent = AnalystAgent(llm_client=FakeLLMClient("analysis notes"))

    with pytest.raises(ValidationError):
        agent.run(state)


def test_analyst_agent_populates_analysis_notes() -> None:
    state = ResearchState(
        request=ResearchQuery(query="Explain multi-agent systems"),
        research_notes="research notes",
    )
    agent = AnalystAgent(llm_client=FakeLLMClient("analysis notes"))

    result = agent.run(state)

    assert result.analysis_notes == "analysis notes"
    assert result.agent_results[-1].agent == "analyst"
    assert result.trace[-1]["name"] == "analyst_completed"


def test_writer_agent_requires_analysis_notes() -> None:
    state = ResearchState(
        request=ResearchQuery(query="Explain multi-agent systems"),
        research_notes="research notes",
    )
    agent = WriterAgent(llm_client=FakeLLMClient("final answer"))

    with pytest.raises(ValidationError):
        agent.run(state)


def test_writer_agent_populates_final_answer() -> None:
    state = ResearchState(
        request=ResearchQuery(query="Explain multi-agent systems"),
        research_notes="research notes",
        analysis_notes="analysis notes",
        sources=[
            SourceDocument(
                title="Source A",
                url="https://example.com/a",
                snippet="Snippet A",
            )
        ],
    )
    agent = WriterAgent(llm_client=FakeLLMClient("final answer"))

    result = agent.run(state)

    assert result.final_answer == "final answer"
    assert result.agent_results[-1].agent == "writer"
    assert result.trace[-1]["name"] == "writer_completed"


def test_critic_agent_requires_final_answer() -> None:
    state = ResearchState(request=ResearchQuery(query="Explain multi-agent systems"))
    agent = CriticAgent(
        llm_client=FakeLLMClient("Quality score: 8\nVerdict: pass\nNotes: grounded")
    )

    with pytest.raises(ValidationError):
        agent.run(state)


def test_critic_agent_populates_review_fields() -> None:
    state = ResearchState(
        request=ResearchQuery(query="Explain multi-agent systems"),
        research_notes="research notes",
        analysis_notes="analysis notes",
        final_answer="Use Source 1 and Source A to support the answer.",
        sources=[
            SourceDocument(
                title="Source A",
                url="https://example.com/a",
                snippet="Snippet A",
            )
        ],
    )
    agent = CriticAgent(
        llm_client=FakeLLMClient("Quality score: 8.5\nVerdict: pass\nNotes: grounded and clear")
    )

    result = agent.run(state)

    assert result.critic_notes is not None
    assert result.quality_score == 8.5
    assert result.citation_coverage == 1.0
    assert result.agent_results[-1].agent == "critic"
    assert result.trace[-1]["name"] == "critic_completed"
