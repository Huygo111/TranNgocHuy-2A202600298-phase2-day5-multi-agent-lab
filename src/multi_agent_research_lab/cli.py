"""Command-line entrypoint for the lab starter."""

import json
from pathlib import Path
from time import perf_counter
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.panel import Panel

from multi_agent_research_lab.core.config import get_settings
from multi_agent_research_lab.core.errors import (
    AgentExecutionError,
    StudentTodoError,
    ValidationError,
)
from multi_agent_research_lab.core.schemas import BenchmarkMetrics, ResearchQuery
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.evaluation.benchmark import load_benchmark_queries, run_benchmark
from multi_agent_research_lab.evaluation.report import render_markdown_report
from multi_agent_research_lab.graph.workflow import MultiAgentWorkflow
from multi_agent_research_lab.observability.logging import configure_logging
from multi_agent_research_lab.observability.tracing import export_trace_artifacts, trace_workflow
from multi_agent_research_lab.services.llm_client import LLMClient
from multi_agent_research_lab.services.storage import LocalArtifactStore

app = typer.Typer(help="Multi-Agent Research Lab starter CLI")
console = Console()


def _init() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)


def _run_baseline_state(
    query: str,
    artifact_name: str = "baseline",
) -> tuple[ResearchState, dict[str, Any], float, dict[str, Any]]:
    request = ResearchQuery(query=query)
    state = ResearchState(request=request)
    llm = LLMClient()

    with trace_workflow(artifact_name, input_payload={"query": request.query}) as trace_info:
        started = perf_counter()
        response = llm.complete(
            system_prompt=(
                "You are a research assistant for technical learners. "
                "Answer thoroughly, structure clearly, and cite sources when available."
            ),
            user_prompt=request.query,
        )
        latency_seconds = perf_counter() - started
        state.final_answer = response.content
        state.add_trace_event(
            "baseline_completion",
            {
                "latency_seconds": round(latency_seconds, 3),
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "cost_usd": response.cost_usd,
            },
        )
        json_trace_path, markdown_trace_path = export_trace_artifacts(
            state,
            artifact_name,
            trace_info=trace_info,
        )

    artifacts = {
        "trace_json_path": json_trace_path,
        "trace_markdown_path": markdown_trace_path,
        "trace_url": trace_info.get("trace_url"),
    }
    return state, trace_info, latency_seconds, artifacts


def _run_multi_agent_state(
    query: str,
    artifact_name: str = "multi-agent",
    *,
    enable_critic: bool | None = None,
) -> tuple[ResearchState, dict[str, Any], dict[str, Any]]:
    state = ResearchState(request=ResearchQuery(query=query))
    workflow = MultiAgentWorkflow(enable_critic=enable_critic)

    with trace_workflow(artifact_name, input_payload={"query": query}) as trace_info:
        result = workflow.run(state)
        json_trace_path, markdown_trace_path = export_trace_artifacts(
            result,
            artifact_name,
            trace_info=trace_info,
        )

    artifacts = {
        "trace_json_path": json_trace_path,
        "trace_markdown_path": markdown_trace_path,
        "trace_url": trace_info.get("trace_url"),
    }
    return result, trace_info, artifacts


@app.command()
def baseline(
    query: Annotated[str, typer.Option("--query", "-q", help="Research query")],
) -> None:
    """Run a minimal single-agent baseline."""

    _init()
    try:
        state, trace_info, latency_seconds, artifacts = _run_baseline_state(
            query,
            artifact_name="baseline-run",
        )
    except (AgentExecutionError, ValidationError) as exc:
        console.print(Panel.fit(str(exc), title="Baseline Error", style="red"))
        raise typer.Exit(code=2) from exc

    trace_payload = state.trace[-1]["payload"] if state.trace else {}

    console.print(Panel.fit(state.final_answer or "", title="Single-Agent Baseline"))
    console.print(
        {
            "latency_seconds": round(latency_seconds, 3),
            "input_tokens": trace_payload.get("input_tokens"),
            "output_tokens": trace_payload.get("output_tokens"),
            "cost_usd": trace_payload.get("cost_usd"),
            "trace_json": artifacts["trace_json_path"],
            "trace_markdown": artifacts["trace_markdown_path"],
            "trace_provider": trace_info.get("provider"),
            "langfuse_trace_url": trace_info.get("trace_url"),
        }
    )


@app.command("multi-agent")
def multi_agent(
    query: Annotated[str, typer.Option("--query", "-q", help="Research query")],
    enable_critic: Annotated[
        bool,
        typer.Option(
            "--enable-critic/--disable-critic",
            help="Enable the optional bonus critic agent for this run",
        ),
    ] = False,
) -> None:
    """Run the multi-agent workflow skeleton."""

    _init()
    try:
        result, trace_info, artifacts = _run_multi_agent_state(
            query,
            artifact_name="multi-agent-run",
            enable_critic=enable_critic,
        )
    except StudentTodoError as exc:
        console.print(Panel.fit(str(exc), title="Expected TODO", style="yellow"))
        raise typer.Exit(code=2) from exc
    console.print(result.model_dump_json(indent=2))
    console.print(
        {
            "trace_json": artifacts["trace_json_path"],
            "trace_markdown": artifacts["trace_markdown_path"],
            "trace_provider": trace_info.get("provider"),
            "langfuse_trace_url": trace_info.get("trace_url"),
        }
    )


@app.command()
def benchmark(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            "-c",
            help="Path to lab YAML config containing benchmark queries",
        ),
    ] = Path("configs/lab_default.yaml"),
    include_critic: Annotated[
        bool,
        typer.Option(
            "--include-critic",
            help="Also run the bonus multi-agent variant with the critic enabled",
        ),
    ] = False,
) -> None:
    """Run benchmark queries for baseline and multi-agent variants and write a report."""

    _init()
    queries = load_benchmark_queries(config)
    if not queries:
        console.print(
            Panel.fit(
                "No benchmark queries found in config.",
                title="Benchmark Error",
                style="red",
            )
        )
        raise typer.Exit(code=2)

    store = LocalArtifactStore()
    metrics: list[BenchmarkMetrics] = []

    def baseline_runner(query: str, run_name: str) -> tuple[ResearchState, dict[str, Any]]:
        state, _trace_info, _latency_seconds, artifacts = _run_baseline_state(
            query,
            artifact_name=run_name,
        )
        return state, artifacts

    def multi_agent_runner(query: str, run_name: str) -> tuple[ResearchState, dict[str, Any]]:
        state, _trace_info, artifacts = _run_multi_agent_state(
            query,
            artifact_name=run_name,
            enable_critic=False,
        )
        return state, artifacts

    def multi_agent_critic_runner(
        query: str,
        run_name: str,
    ) -> tuple[ResearchState, dict[str, Any]]:
        state, _trace_info, artifacts = _run_multi_agent_state(
            query,
            artifact_name=run_name,
            enable_critic=True,
        )
        return state, artifacts

    runners = [
        ("baseline", baseline_runner),
        ("multi-agent", multi_agent_runner),
    ]
    if include_critic:
        runners.append(("multi-agent-critic", multi_agent_critic_runner))

    for index, query in enumerate(queries, start=1):
        for variant, runner in runners:
            run_name = f"{variant}-benchmark-{index}"
            state, benchmark_metrics = run_benchmark(run_name, query, runner)
            benchmark_metrics.variant = variant
            metrics.append(benchmark_metrics)
            if state is None:
                console.print(
                    Panel.fit(
                        f"{variant} failed on query {index}: {benchmark_metrics.notes}",
                        title="Benchmark Run",
                        style="yellow",
                    )
                )
                continue
            console.print(
                {
                    "variant": variant,
                    "query_index": index,
                    "latency_seconds": round(benchmark_metrics.latency_seconds, 3),
                    "cost_usd": benchmark_metrics.estimated_cost_usd,
                    "citation_coverage": benchmark_metrics.citation_coverage,
                    "trace_markdown": benchmark_metrics.trace_markdown_path,
                    "langfuse_trace_url": benchmark_metrics.trace_url,
                }
            )

    report_markdown = render_markdown_report(metrics)
    report_path = store.write_text("benchmark_report.md", report_markdown)
    metrics_path = store.write_text(
        "benchmark_metrics.json",
        json.dumps(
            [item.model_dump(mode="json") for item in metrics],
            indent=2,
            ensure_ascii=False,
        ),
    )

    console.print(
        {
            "report_markdown": str(report_path),
            "metrics_json": str(metrics_path),
            "runs": len(metrics),
            "queries": len(queries),
        }
    )


if __name__ == "__main__":
    app()
