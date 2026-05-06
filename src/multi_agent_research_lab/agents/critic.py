"""Optional critic agent for bonus quality checks."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Protocol

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.errors import ValidationError
from multi_agent_research_lab.core.schemas import AgentName, AgentResult
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.services.llm_client import LLMClient, LLMResponse


class SupportsCompletion(Protocol):
    def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse: ...


class CriticAgent(BaseAgent):
    """Review the final answer for grounding and citation quality."""

    name = "critic"

    def __init__(self, llm_client: SupportsCompletion | None = None) -> None:
        self._llm_client = llm_client or LLMClient()

    def run(self, state: ResearchState) -> ResearchState:
        """Populate critic notes, citation coverage, and a quality score."""

        if not state.final_answer:
            raise ValidationError("final_answer is required before running CriticAgent")

        source_references = "\n".join(
            f"- {source.title} ({source.url or 'no-url'})"
            for source in state.sources
        )
        response = self._llm_client.complete(
            system_prompt=(
                "You are a critic reviewing a research answer. Check grounding, citation use, "
                "and clarity. Return exactly three lines in this format:\n"
                "Quality score: <0-10>\n"
                "Verdict: <pass or needs_revision>\n"
                "Notes: <short review>"
            ),
            user_prompt=(
                f"Query: {state.request.query}\n"
                f"Final answer:\n{state.final_answer}\n\n"
                f"Research notes:\n{state.research_notes or '(none)'}\n\n"
                f"Analysis notes:\n{state.analysis_notes or '(none)'}\n\n"
                f"Sources:\n{source_references or '(none)'}"
            ),
        )

        quality_score = _extract_quality_score(response.content)
        citation_coverage = _estimate_citation_coverage(state.final_answer, state.sources)

        state.critic_notes = response.content
        state.quality_score = quality_score
        state.citation_coverage = citation_coverage
        state.agent_results.append(
            AgentResult(
                agent=AgentName.CRITIC,
                content=response.content,
                metadata={
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                    "cost_usd": response.cost_usd,
                    "quality_score": quality_score,
                    "citation_coverage": citation_coverage,
                },
            )
        )
        state.add_trace_event(
            "critic_completed",
            {
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "cost_usd": response.cost_usd,
                "quality_score": quality_score,
                "citation_coverage": citation_coverage,
            },
        )
        return state


def _extract_quality_score(review: str) -> float | None:
    match = re.search(r"quality score:\s*([0-9]+(?:\.[0-9]+)?)", review, flags=re.IGNORECASE)
    if match is None:
        return None

    score = float(match.group(1))
    if score < 0:
        return 0.0
    if score > 10:
        return 10.0
    return score


def _estimate_citation_coverage(final_answer: str, sources: Sequence[object]) -> float:
    if not final_answer or not sources:
        return 0.0

    matched_sources = 0
    for index, source in enumerate(sources, start=1):
        title = getattr(source, "title", "")
        url = getattr(source, "url", None)
        if title and title in final_answer:
            matched_sources += 1
            continue
        if f"Source {index}" in final_answer:
            matched_sources += 1
            continue
        if url and url in final_answer:
            matched_sources += 1

    return matched_sources / len(sources)
