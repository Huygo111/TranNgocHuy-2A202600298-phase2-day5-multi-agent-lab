"""LangGraph workflow skeleton."""

from typing import Any

from langgraph.graph import END, StateGraph

from multi_agent_research_lab.agents.analyst import AnalystAgent
from multi_agent_research_lab.agents.critic import CriticAgent
from multi_agent_research_lab.agents.researcher import ResearcherAgent
from multi_agent_research_lab.agents.supervisor import SupervisorAgent
from multi_agent_research_lab.agents.writer import WriterAgent
from multi_agent_research_lab.core.state import ResearchState


class MultiAgentWorkflow:
    """Builds and runs the multi-agent graph.

    Keep orchestration here; keep agent internals in `agents/`.
    """

    def __init__(self, enable_critic: bool | None = None) -> None:
        self._enable_critic = enable_critic

    def build(self) -> Any:
        """Create a LangGraph graph.

        Build the core Supervisor -> Worker -> Supervisor loop.
        """

        graph = StateGraph(ResearchState)

        graph.add_node("supervisor", SupervisorAgent(enable_critic=self._enable_critic).run)
        graph.add_node("researcher", ResearcherAgent().run)
        graph.add_node("analyst", AnalystAgent().run)
        graph.add_node("writer", WriterAgent().run)
        graph.add_node("critic", CriticAgent().run)

        graph.set_entry_point("supervisor")

        def router(state: ResearchState) -> str:
            last_route = state.route_history[-1] if state.route_history else "done"
            return END if last_route == "done" else last_route

        graph.add_conditional_edges(
            "supervisor",
            router,
            {
                "researcher": "researcher",
                "analyst": "analyst",
                "writer": "writer",
                "critic": "critic",
                END: END,
            },
        )

        for node in ["researcher", "analyst", "writer", "critic"]:
            graph.add_edge(node, "supervisor")

        return graph.compile()

    def run(self, state: ResearchState) -> ResearchState:
        """Execute the graph and return final state.

        Compile graph, invoke it, and normalize the result back to ResearchState.
        """

        compiled = self.build()
        result = compiled.invoke(state)
        if isinstance(result, ResearchState):
            return result
        return ResearchState.model_validate(result)
