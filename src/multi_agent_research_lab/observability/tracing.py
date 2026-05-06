"""Tracing hooks.

This file intentionally avoids binding to one provider. Students can plug in LangSmith,
Langfuse, OpenTelemetry, or simple JSON traces.
"""

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import import_module
from time import perf_counter
from typing import Any

from multi_agent_research_lab.core.config import get_settings
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.services.storage import LocalArtifactStore


@contextmanager
def trace_span(name: str, attributes: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
    """Minimal span context used by the skeleton.

    TODO(student): Replace or augment with LangSmith/Langfuse provider spans.
    """

    started = perf_counter()
    span: dict[str, Any] = {"name": name, "attributes": attributes or {}, "duration_seconds": None}
    try:
        yield span
    finally:
        span["duration_seconds"] = perf_counter() - started


@contextmanager
def trace_workflow(
    name: str,
    *,
    input_payload: dict[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    """Wrap a run in a Langfuse span when configured, otherwise fall back to local timing."""

    trace_info: dict[str, Any] = {
        "provider": "local",
        "trace_id": None,
        "trace_url": None,
    }
    langfuse_client = _get_langfuse_client()
    if langfuse_client is None:
        with trace_span(name, input_payload) as local_span:
            trace_info["local_span"] = local_span
            yield trace_info
        return

    with langfuse_client.start_as_current_observation(as_type="span", name=name) as observation:
        if input_payload is not None:
            observation.update(input=input_payload)
        trace_info["provider"] = "langfuse"
        try:
            trace_info["trace_id"] = langfuse_client.get_current_trace_id()
            trace_info["trace_url"] = langfuse_client.get_trace_url()
        except Exception as exc:
            trace_info["provider"] = "langfuse_error"
            trace_info["trace_error"] = str(exc)
            trace_info["trace_id"] = None
            trace_info["trace_url"] = None
        try:
            yield trace_info
        finally:
            try:
                langfuse_client.flush()
            except Exception as exc:
                trace_info["flush_error"] = str(exc)


def render_trace_summary(
    state: ResearchState,
    trace_info: dict[str, Any] | None = None,
) -> str:
    """Render a compact, human-readable trace summary."""

    lines = [
        "# Trace Summary",
        "",
        f"Query: {state.request.query}",
        f"Iterations: {state.iteration}",
        f"Route history: {' -> '.join(state.route_history) if state.route_history else '(empty)'}",
        "",
    ]
    if trace_info is not None:
        lines.extend(
            [
                "## External Trace",
                f"Provider: {trace_info.get('provider', 'local')}",
                f"Trace ID: {trace_info.get('trace_id') or '(not available)'}",
                f"Trace URL: {trace_info.get('trace_url') or '(not available)'}",
                "",
            ]
        )

    lines.extend(
        [
            "## Events",
        ]
    )
    for index, event in enumerate(state.trace, start=1):
        payload = json.dumps(event["payload"], ensure_ascii=False)
        lines.append(f"{index}. {event['name']}: {payload}")
    lines.append("")
    return "\n".join(lines)


def export_trace_artifacts(
    state: ResearchState,
    run_name: str,
    store: LocalArtifactStore | None = None,
    trace_info: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Write trace artifacts to local reports storage and return relative paths."""

    artifact_store = store or LocalArtifactStore()
    slug = _slugify(run_name)
    json_relative_path = f"traces/{slug}.json"
    md_relative_path = f"traces/{slug}.md"

    artifact_store.write_text(
        json_relative_path,
        state.model_dump_json(indent=2),
    )
    artifact_store.write_text(
        md_relative_path,
        render_trace_summary(state, trace_info=trace_info),
    )
    return json_relative_path, md_relative_path


def get_langfuse_trace_url() -> str | None:
    client = _get_langfuse_client()
    if client is None:
        return None
    trace_url = client.get_trace_url()
    return trace_url if isinstance(trace_url, str) else None


def _slugify(value: str) -> str:
    cleaned = "".join(character.lower() if character.isalnum() else "-" for character in value)
    compact = "-".join(part for part in cleaned.split("-") if part)
    return compact or "trace"


def _get_langfuse_client() -> Any | None:
    settings = get_settings()
    if not (
        settings.langfuse_enabled
        and settings.langfuse_public_key
        and settings.langfuse_secret_key
    ):
        return None

    os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key
    os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key
    os.environ["LANGFUSE_BASE_URL"] = settings.langfuse_base_url

    try:
        langfuse_module = import_module("langfuse")
    except ImportError:
        return None
    return langfuse_module.get_client()
