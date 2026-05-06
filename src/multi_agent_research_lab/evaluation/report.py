"""Benchmark report rendering."""

from __future__ import annotations

from collections import defaultdict

from multi_agent_research_lab.core.schemas import BenchmarkMetrics


def render_markdown_report(metrics: list[BenchmarkMetrics]) -> str:
    """Render benchmark metrics to markdown with per-run and aggregate summaries."""

    lines = [
        "# Benchmark Report",
        "",
        "## Per-Run Results",
        "",
        (
            "| Variant | Query | Latency (s) | Cost (USD) | Quality Score | "
            "Citation Coverage | Failed | Notes |"
        ),
        "|---|---|---:|---:|---:|---:|---|---|",
    ]
    for item in metrics:
        cost = "" if item.estimated_cost_usd is None else f"{item.estimated_cost_usd:.4f}"
        quality = "" if item.quality_score is None else f"{item.quality_score:.1f}"
        coverage = "" if item.citation_coverage is None else f"{item.citation_coverage:.2f}"
        query = "" if item.query is None else _shorten(item.query, 60)
        lines.append(
            f"| {item.variant or item.run_name} | {query} | {item.latency_seconds:.2f} | "
            f"{cost} | {quality} | {coverage} | {'yes' if item.failed else 'no'} | {item.notes} |"
        )

    lines.extend(
        [
            "",
            "## Aggregate Summary",
            "",
            (
                "| Variant | Runs | Avg Latency (s) | Avg Cost (USD) | Avg Quality Score | "
                "Avg Citation Coverage | Failure Rate |"
            ),
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )

    for variant, items in _group_by_variant(metrics).items():
        lines.append(
            f"| {variant} | {len(items)} | {_avg_latency(items):.2f} | "
            f"{_format_optional(_avg_cost(items), decimals=4)} | "
            f"{_format_optional(_avg_quality(items), decimals=2)} | "
            f"{_format_optional(_avg_coverage(items), decimals=2)} | "
            f"{_failure_rate(items):.2f} |"
        )

    lines.extend(
        [
            "",
            "## Trace Artifacts",
            "",
        ]
    )
    for item in metrics:
        label = f"{item.variant or item.run_name}: {_shorten(item.query or '', 60)}"
        if item.trace_markdown_path:
            lines.append(f"- {label} -> `{item.trace_markdown_path}`")

    return "\n".join(lines) + "\n"


def _group_by_variant(metrics: list[BenchmarkMetrics]) -> dict[str, list[BenchmarkMetrics]]:
    grouped: defaultdict[str, list[BenchmarkMetrics]] = defaultdict(list)
    for item in metrics:
        grouped[item.variant or item.run_name].append(item)
    return dict(grouped)


def _avg_latency(metrics: list[BenchmarkMetrics]) -> float:
    return sum(item.latency_seconds for item in metrics) / len(metrics)


def _avg_cost(metrics: list[BenchmarkMetrics]) -> float | None:
    values = [item.estimated_cost_usd for item in metrics if item.estimated_cost_usd is not None]
    if not values:
        return None
    return sum(values) / len(values)


def _avg_coverage(metrics: list[BenchmarkMetrics]) -> float | None:
    values = [item.citation_coverage for item in metrics if item.citation_coverage is not None]
    if not values:
        return None
    return sum(values) / len(values)


def _avg_quality(metrics: list[BenchmarkMetrics]) -> float | None:
    values = [item.quality_score for item in metrics if item.quality_score is not None]
    if not values:
        return None
    return sum(values) / len(values)


def _failure_rate(metrics: list[BenchmarkMetrics]) -> float:
    failures = sum(1 for item in metrics if item.failed)
    return failures / len(metrics)


def _format_optional(value: float | None, *, decimals: int = 2) -> str:
    if value is None:
        return ""
    return f"{value:.{decimals}f}"


def _shorten(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
