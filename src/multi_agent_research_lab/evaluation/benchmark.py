"""Benchmark helpers for single-agent vs multi-agent runs."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from typing import Any

import yaml  # type: ignore[import-untyped]

from multi_agent_research_lab.core.schemas import BenchmarkMetrics
from multi_agent_research_lab.core.state import ResearchState

Runner = Callable[[str, str], tuple[ResearchState, dict[str, Any]]]


def run_benchmark(
    run_name: str,
    query: str,
    runner: Runner,
) -> tuple[ResearchState | None, BenchmarkMetrics]:
    """Measure one benchmark run and collect core metrics."""

    started = perf_counter()
    try:
        state, run_metadata = runner(query, run_name)
    except Exception as exc:
        latency = perf_counter() - started
        metrics = BenchmarkMetrics(
            run_name=run_name,
            variant=run_name,
            query=query,
            latency_seconds=latency,
            failed=True,
            notes=f"Failed: {exc}",
        )
        return None, metrics

    latency = perf_counter() - started
    metrics = BenchmarkMetrics(
        run_name=run_name,
        variant=run_name,
        query=query,
        latency_seconds=latency,
        estimated_cost_usd=_estimate_state_cost(state),
        quality_score=state.quality_score,
        citation_coverage=_estimate_citation_coverage(state),
        failed=False,
        notes=_summarize_run(state),
        trace_json_path=_coerce_optional_string(run_metadata.get("trace_json_path")),
        trace_markdown_path=_coerce_optional_string(run_metadata.get("trace_markdown_path")),
        trace_url=_coerce_optional_string(run_metadata.get("trace_url")),
    )
    return state, metrics


def load_benchmark_queries(config_path: str | Path) -> list[str]:
    """Load benchmark queries from the lab YAML config."""

    data = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    queries = data.get("benchmark", {}).get("queries", [])
    if not isinstance(queries, list):
        return []
    return [str(query) for query in queries]


def _estimate_state_cost(state: ResearchState) -> float | None:
    costs = [
        float(result.metadata["cost_usd"])
        for result in state.agent_results
        if result.metadata.get("cost_usd") is not None
    ]
    if not costs and state.trace:
        fallback_costs = [
            float(event["payload"]["cost_usd"])
            for event in state.trace
            if event["payload"].get("cost_usd") is not None
        ]
        return sum(fallback_costs) if fallback_costs else None
    return sum(costs) if costs else None


def _estimate_citation_coverage(state: ResearchState) -> float | None:
    if state.citation_coverage is not None:
        return state.citation_coverage
    if not state.final_answer:
        return 0.0
    if not state.sources:
        return 0.0

    matched_sources = 0
    for index, source in enumerate(state.sources, start=1):
        title_in_answer = source.title in state.final_answer
        label_in_answer = f"Source {index}" in state.final_answer
        url_in_answer = bool(source.url and source.url in state.final_answer)
        if title_in_answer or label_in_answer or url_in_answer:
            matched_sources += 1

    return matched_sources / len(state.sources)


def _summarize_run(state: ResearchState) -> str:
    route = " -> ".join(state.route_history) if state.route_history else "no-routes"
    source_count = len(state.sources)
    critic = "yes" if state.critic_notes else "no"
    return f"route={route}; sources={source_count}; critic={critic}; errors={len(state.errors)}"


def _coerce_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
