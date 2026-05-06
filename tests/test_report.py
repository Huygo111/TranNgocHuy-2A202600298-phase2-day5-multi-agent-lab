from multi_agent_research_lab.core.schemas import BenchmarkMetrics
from multi_agent_research_lab.evaluation.report import render_markdown_report


def test_report_renders_markdown() -> None:
    report = render_markdown_report(
        [
            BenchmarkMetrics(
                run_name="baseline-benchmark-1",
                variant="baseline",
                query="Explain multi-agent systems",
                latency_seconds=1.23,
                citation_coverage=0.5,
                trace_markdown_path="traces/baseline-benchmark-1.md",
            )
        ]
    )
    assert "Benchmark Report" in report
    assert "baseline" in report
    assert "Aggregate Summary" in report
    assert "traces/baseline-benchmark-1.md" in report
