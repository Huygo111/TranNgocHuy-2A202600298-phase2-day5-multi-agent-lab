from types import SimpleNamespace

import pytest

from multi_agent_research_lab.agents import SupervisorAgent
from multi_agent_research_lab.core.schemas import ResearchQuery
from multi_agent_research_lab.core.state import ResearchState


def test_supervisor_routes_to_researcher_first(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "multi_agent_research_lab.agents.supervisor.get_settings",
        lambda: SimpleNamespace(max_iterations=6, enable_critic=False),
    )
    state = ResearchState(request=ResearchQuery(query="Explain multi-agent systems"))

    result = SupervisorAgent().run(state)

    assert result.route_history == ["researcher"]
    assert result.trace[-1]["payload"]["next"] == "researcher"


def test_supervisor_routes_to_done_when_final_answer_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "multi_agent_research_lab.agents.supervisor.get_settings",
        lambda: SimpleNamespace(max_iterations=6, enable_critic=False),
    )
    state = ResearchState(
        request=ResearchQuery(query="Explain multi-agent systems"),
        research_notes="notes",
        analysis_notes="analysis",
        final_answer="done",
    )

    result = SupervisorAgent().run(state)

    assert result.route_history == ["done"]


def test_supervisor_routes_to_critic_when_bonus_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "multi_agent_research_lab.agents.supervisor.get_settings",
        lambda: SimpleNamespace(max_iterations=6, enable_critic=True),
    )
    state = ResearchState(
        request=ResearchQuery(query="Explain multi-agent systems"),
        research_notes="notes",
        analysis_notes="analysis",
        final_answer="final answer",
    )

    result = SupervisorAgent().run(state)

    assert result.route_history == ["critic"]


def test_supervisor_stops_when_max_iterations_reached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "multi_agent_research_lab.agents.supervisor.get_settings",
        lambda: SimpleNamespace(max_iterations=1, enable_critic=False),
    )
    state = ResearchState(
        request=ResearchQuery(query="Explain multi-agent systems"),
        iteration=1,
    )

    result = SupervisorAgent().run(state)

    assert result.route_history == ["done"]
