"""evals.logistics.task — LogisticsTask: system-under-test adapter.

Invokes the full LogisticsGraph so the eval exercises the same two-phase
path as the live system: ReAct loop (logistics_agent) → structured output
(extract_plan).

Tool injection
──────────────
Each LogisticsCase carries mock_tools — a list of callables built from the
case's authored tool_responses. These are passed directly to
build_logistics_agent_graph(tools=...) so the LLM experiences a full tool
call/response cycle without a live database. The graph wiring is identical
to production; only the tool implementations differ.

No data_store or world_engine is required:
  - tools are injected per-case (see above)
  - sector_analysis node is disabled; world_engine is never accessed
  - advisory_repo=None (via data_store=None) prevents DB writes
"""

from __future__ import annotations

import asyncio
from agents.commons.agent_dependencies import AgentDependencies
from agents.logistics.graph import build_logistics_agent_graph
from agents.logistics.state import LogisticsAgentState, LogisticsAssessment
from evals.logistics.cases import LogisticsCase
from evals.framework.core import Usage


class LogisticsTask:
    """Task[LogisticsCase, LogisticsAssessment] — runs one case through the full LogisticsGraph."""

    def __init__(
        self,
        *,
        prompt_registry,
        llm_registry,
        prompt_version: str = "v1",
    ) -> None:
        self.label = f"logistics-graph/{prompt_version}"
        # model_construct bypasses Pydantic's isinstance check on world_engine.
        # Safe because sector_analysis is disabled and the engine is never accessed.
        self._deps = AgentDependencies.model_construct(
            llm_registry=llm_registry,
            prompt_registry=prompt_registry,
            world_engine=None,
            data_store=None,
        )

    async def run(self, case: LogisticsCase) -> tuple[LogisticsAssessment | None, Usage]:
        graph = build_logistics_agent_graph(
            agent_deps=self._deps,
            tools=case.build_mock_tools(),
        )
        state = LogisticsAgentState(
            situation_summary=case.situation_summary,
            escalations=case.escalations,
        )
        result = await asyncio.to_thread(graph.invoke, state)
        assessment: LogisticsAssessment | None = result.get("logistics_assessment")
        # Per-run token count not available from the graph; aggregate captured
        # by llm_registry.usage_report() at the end of the eval run.
        return assessment, Usage(total_tokens=0)
