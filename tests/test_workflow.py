from types import SimpleNamespace

import pytest

from multi_agent_research_lab.core.schemas import ResearchQuery
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.graph.workflow import MultiAgentWorkflow


def test_workflow_build_returns_compiled_graph() -> None:
    workflow = MultiAgentWorkflow()

    compiled = workflow.build()

    assert compiled is not None


def test_workflow_run_cycles_through_core_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "multi_agent_research_lab.graph.workflow.ResearcherAgent.run",
        lambda self, state: _set_research_notes(state),
    )
    monkeypatch.setattr(
        "multi_agent_research_lab.graph.workflow.AnalystAgent.run",
        lambda self, state: _set_analysis_notes(state),
    )
    monkeypatch.setattr(
        "multi_agent_research_lab.graph.workflow.WriterAgent.run",
        lambda self, state: _set_final_answer(state),
    )

    state = ResearchState(request=ResearchQuery(query="Explain multi-agent systems"))
    result = MultiAgentWorkflow(enable_critic=False).run(state)

    assert result.research_notes == "research complete"
    assert result.analysis_notes == "analysis complete"
    assert result.final_answer == "final answer"
    assert result.route_history == ["researcher", "analyst", "writer", "done"]


def test_workflow_can_route_through_critic_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "multi_agent_research_lab.agents.supervisor.get_settings",
        lambda: SimpleNamespace(max_iterations=6, enable_critic=True),
    )
    monkeypatch.setattr(
        "multi_agent_research_lab.graph.workflow.ResearcherAgent.run",
        lambda self, state: _set_research_notes(state),
    )
    monkeypatch.setattr(
        "multi_agent_research_lab.graph.workflow.AnalystAgent.run",
        lambda self, state: _set_analysis_notes(state),
    )
    monkeypatch.setattr(
        "multi_agent_research_lab.graph.workflow.WriterAgent.run",
        lambda self, state: _set_final_answer(state),
    )
    monkeypatch.setattr(
        "multi_agent_research_lab.graph.workflow.CriticAgent.run",
        lambda self, state: _set_critic_notes(state),
    )

    state = ResearchState(request=ResearchQuery(query="Explain multi-agent systems"))
    result = MultiAgentWorkflow().run(state)

    assert result.critic_notes == "critic review"
    assert result.route_history == ["researcher", "analyst", "writer", "critic", "done"]


def _set_research_notes(state: ResearchState) -> ResearchState:
    state.research_notes = "research complete"
    return state


def _set_analysis_notes(state: ResearchState) -> ResearchState:
    state.analysis_notes = "analysis complete"
    return state


def _set_final_answer(state: ResearchState) -> ResearchState:
    state.final_answer = "final answer"
    return state


def _set_critic_notes(state: ResearchState) -> ResearchState:
    state.critic_notes = "critic review"
    state.quality_score = 8.5
    state.citation_coverage = 1.0
    return state
