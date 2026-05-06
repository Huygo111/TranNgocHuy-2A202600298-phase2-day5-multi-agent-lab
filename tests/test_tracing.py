from pathlib import Path

from multi_agent_research_lab.core.schemas import ResearchQuery
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.observability.tracing import (
    export_trace_artifacts,
    render_trace_summary,
)
from multi_agent_research_lab.services.storage import LocalArtifactStore


def test_render_trace_summary_includes_routes_and_events() -> None:
    state = ResearchState(request=ResearchQuery(query="Explain multi-agent systems"))
    state.record_route("researcher")
    state.add_trace_event("researcher_completed", {"source_count": 3})

    summary = render_trace_summary(
        state,
        trace_info={"provider": "langfuse", "trace_id": "abc123", "trace_url": "https://example.com"},
    )

    assert "Trace Summary" in summary
    assert "researcher" in summary
    assert "researcher_completed" in summary
    assert "https://example.com" in summary


def test_export_trace_artifacts_writes_json_and_markdown() -> None:
    state = ResearchState(request=ResearchQuery(query="Explain multi-agent systems"))
    state.record_route("done")
    state.add_trace_event("baseline_completion", {"latency_seconds": 1.23})
    artifact_root = Path(".test_artifacts")
    store = LocalArtifactStore(root=artifact_root)

    json_relative_path, markdown_relative_path = export_trace_artifacts(
        state,
        "baseline run",
        store=store,
    )

    json_path = artifact_root / json_relative_path
    markdown_path = artifact_root / markdown_relative_path

    assert json_path.exists()
    assert markdown_path.exists()
    assert "baseline-run" in json_relative_path
    assert "Trace Summary" in markdown_path.read_text(encoding="utf-8")
