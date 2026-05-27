"""evals.logistics.task — LogisticsTask: system-under-test adapter.

Invokes the full LogisticsGraph so the eval exercises the same two-phase
path as the live system: ReAct loop (logistics_agent) → structured output
(extract_plan).

Dependencies deliberately minimal:
  - data_store=None   → no DB writes; tool calls (get_resources_within,
                        get_wildfire_activity) are skipped, so the LLM
                        reasons from the authored sector analysis alone.
  - world_engine=stub → sector_analysis node is disabled in the current
                        graph; the engine is never accessed.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

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
        deps = AgentDependencies(
            llm_registry=llm_registry,
            prompt_registry=prompt_registry,
            world_engine=MagicMock(),  # sector_analysis disabled; never accessed
            data_store=None,           # no DB writes; tools skipped gracefully
        )
        self._graph = build_logistics_agent_graph(agent_deps=deps)

    async def run(self, case: LogisticsCase) -> tuple[LogisticsAssessment | None, Usage]:
        state = LogisticsAgentState(
            situation_summary=case.situation_summary,
            escalations=case.escalations,
        )
        result = await asyncio.to_thread(self._graph.invoke, state)
        assessment: LogisticsAssessment | None = result.get("logistics_assessment")
        # Per-run token count not available from the graph; aggregate captured
        # by llm_registry.usage_report() at the end of the eval run.
        return assessment, Usage(total_tokens=0)
