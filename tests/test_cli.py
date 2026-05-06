from pathlib import Path

import pytest
from typer.testing import CliRunner

from multi_agent_research_lab.cli import app
from multi_agent_research_lab.core.errors import ValidationError
from multi_agent_research_lab.core.schemas import ResearchQuery
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.services.llm_client import LLMResponse

runner = CliRunner()


def test_baseline_command_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeLLMClient:
        def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
            assert "research assistant" in system_prompt
            assert user_prompt == "Explain multi-agent systems"
            return LLMResponse(
                content="Baseline answer",
                input_tokens=10,
                output_tokens=20,
                cost_usd=0.001,
            )

    monkeypatch.setattr("multi_agent_research_lab.cli.LLMClient", FakeLLMClient)

    result = runner.invoke(
        app,
        ["baseline", "--query", "Explain multi-agent systems"],
    )

    assert result.exit_code == 0
    assert "Baseline answer" in result.stdout
    assert "latency_seconds" in result.stdout


def test_baseline_command_reports_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeLLMClient:
        def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
            raise ValidationError("OPENAI_API_KEY is required")

    monkeypatch.setattr("multi_agent_research_lab.cli.LLMClient", FakeLLMClient)

    result = runner.invoke(
        app,
        ["baseline", "--query", "Explain multi-agent systems"],
    )

    assert result.exit_code == 2
    assert "OPENAI_API_KEY is required" in result.stdout


def test_multi_agent_command_passes_enable_critic(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_multi_agent_state(
        query: str,
        artifact_name: str = "multi-agent",
        *,
        enable_critic: bool | None = None,
    ) -> tuple[ResearchState, dict[str, object], dict[str, object]]:
        captured["query"] = query
        captured["artifact_name"] = artifact_name
        captured["enable_critic"] = enable_critic
        state = ResearchState(request=ResearchQuery(query=query), final_answer="final")
        return (
            state,
            {"provider": "local", "trace_url": None},
            {
                "trace_json_path": f"traces/{artifact_name}.json",
                "trace_markdown_path": f"traces/{artifact_name}.md",
                "trace_url": None,
            },
        )

    monkeypatch.setattr(
        "multi_agent_research_lab.cli._run_multi_agent_state",
        fake_run_multi_agent_state,
    )

    result = runner.invoke(
        app,
        ["multi-agent", "--query", "Explain multi-agent systems", "--enable-critic"],
    )

    assert result.exit_code == 0
    assert captured["enable_critic"] is True


def test_benchmark_command_writes_report(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_load_benchmark_queries(_config: Path) -> list[str]:
        return ["Explain multi-agent systems"]

    def fake_run_baseline_state(
        query: str,
        artifact_name: str = "baseline",
    ) -> tuple[ResearchState, dict[str, object], float, dict[str, object]]:
        state = ResearchState(request=ResearchQuery(query=query))
        state.final_answer = "Baseline answer"
        state.add_trace_event("baseline_completion", {"cost_usd": 0.001})
        return (
            state,
            {"provider": "local", "trace_url": None},
            0.5,
            {
                "trace_json_path": f"traces/{artifact_name}.json",
                "trace_markdown_path": f"traces/{artifact_name}.md",
                "trace_url": None,
            },
        )

    def fake_run_multi_agent_state(
        query: str,
        artifact_name: str = "multi-agent",
    ) -> tuple[ResearchState, dict[str, object], dict[str, object]]:
        state = ResearchState(request=ResearchQuery(query=query))
        state.record_route("researcher")
        state.record_route("analyst")
        state.record_route("writer")
        state.record_route("done")
        state.final_answer = "Multi-agent answer with Source 1"
        state.sources = []
        return (
            state,
            {"provider": "local", "trace_url": None},
            {
                "trace_json_path": f"traces/{artifact_name}.json",
                "trace_markdown_path": f"traces/{artifact_name}.md",
                "trace_url": None,
            },
        )

    monkeypatch.setattr(
        "multi_agent_research_lab.cli.load_benchmark_queries",
        fake_load_benchmark_queries,
    )
    monkeypatch.setattr(
        "multi_agent_research_lab.cli._run_baseline_state",
        fake_run_baseline_state,
    )
    monkeypatch.setattr(
        "multi_agent_research_lab.cli._run_multi_agent_state",
        fake_run_multi_agent_state,
    )
    from multi_agent_research_lab.services.storage import LocalArtifactStore

    artifact_root = Path(".test_benchmark_artifacts")
    monkeypatch.setattr(
        "multi_agent_research_lab.cli.LocalArtifactStore",
        lambda: LocalArtifactStore(root=artifact_root),
    )

    result = runner.invoke(app, ["benchmark"])

    assert result.exit_code == 0
    assert "benchmark_report.md" in result.stdout
    assert (artifact_root / "benchmark_report.md").exists()
    assert (artifact_root / "benchmark_metrics.json").exists()


def test_benchmark_command_can_include_critic_variant(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_load_benchmark_queries(_config: Path) -> list[str]:
        return ["Explain multi-agent systems"]

    def fake_run_baseline_state(
        query: str,
        artifact_name: str = "baseline",
    ) -> tuple[ResearchState, dict[str, object], float, dict[str, object]]:
        state = ResearchState(request=ResearchQuery(query=query), final_answer="Baseline answer")
        return (
            state,
            {"provider": "local", "trace_url": None},
            0.5,
            {
                "trace_json_path": f"traces/{artifact_name}.json",
                "trace_markdown_path": f"traces/{artifact_name}.md",
                "trace_url": None,
            },
        )

    calls: list[bool | None] = []

    def fake_run_multi_agent_state(
        query: str,
        artifact_name: str = "multi-agent",
        *,
        enable_critic: bool | None = None,
    ) -> tuple[ResearchState, dict[str, object], dict[str, object]]:
        calls.append(enable_critic)
        state = ResearchState(
            request=ResearchQuery(query=query),
            final_answer="Multi-agent answer with Source 1",
            citation_coverage=1.0,
            quality_score=8.0 if enable_critic else None,
            critic_notes="review" if enable_critic else None,
        )
        return (
            state,
            {"provider": "local", "trace_url": None},
            {
                "trace_json_path": f"traces/{artifact_name}.json",
                "trace_markdown_path": f"traces/{artifact_name}.md",
                "trace_url": None,
            },
        )

    monkeypatch.setattr(
        "multi_agent_research_lab.cli.load_benchmark_queries",
        fake_load_benchmark_queries,
    )
    monkeypatch.setattr(
        "multi_agent_research_lab.cli._run_baseline_state",
        fake_run_baseline_state,
    )
    monkeypatch.setattr(
        "multi_agent_research_lab.cli._run_multi_agent_state",
        fake_run_multi_agent_state,
    )
    from multi_agent_research_lab.services.storage import LocalArtifactStore

    artifact_root = Path(".test_benchmark_artifacts_critic")
    monkeypatch.setattr(
        "multi_agent_research_lab.cli.LocalArtifactStore",
        lambda: LocalArtifactStore(root=artifact_root),
    )

    result = runner.invoke(app, ["benchmark", "--include-critic"])

    assert result.exit_code == 0
    assert calls == [False, True]
