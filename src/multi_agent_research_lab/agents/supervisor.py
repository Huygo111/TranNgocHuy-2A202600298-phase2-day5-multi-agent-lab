"""Supervisor / router skeleton."""

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.config import get_settings
from multi_agent_research_lab.core.state import ResearchState


class SupervisorAgent(BaseAgent):
    """Decides which worker should run next and when to stop."""

    name = "supervisor"

    def __init__(self, enable_critic: bool | None = None) -> None:
        self._enable_critic = enable_critic

    def run(self, state: ResearchState) -> ResearchState:
        """Update `state.route_history` with the next route.

        Inspect the current state and choose the next worker or stop.
        """

        settings = get_settings()
        enable_critic = (
            settings.enable_critic if self._enable_critic is None else self._enable_critic
        )

        if state.iteration >= settings.max_iterations:
            next_route = "done"
        elif not state.research_notes:
            next_route = "researcher"
        elif not state.analysis_notes:
            next_route = "analyst"
        elif not state.final_answer:
            next_route = "writer"
        elif enable_critic and not state.critic_notes:
            next_route = "critic"
        else:
            next_route = "done"

        state.record_route(next_route)
        state.add_trace_event(
            "supervisor_route",
            {"next": next_route, "iteration": state.iteration},
        )
        return state
