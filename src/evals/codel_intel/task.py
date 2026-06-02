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

import logging

from pydantic import BaseModel, Field

from agents.commons.agent_dependencies import AgentDependencies
from code_intel.agent.graph import build_code_intel_graph
from code_intel.agent.state import CodeIntelState, RetrievedChunk
from code_intel.process_files.embedder import Embedder
from evals.codel_intel.cases import RAGRetrievalCase
from evals.framework.core import Usage
from stores.postgres import get_pg_gateway
from stores.postgres.code_intel_repo import CodeIntelRepo

logging.basicConfig(level=logging.WARNING)


class RAGRetrievalOutput(BaseModel):
    """One run's product, carrying both eval layers' raw material.

    ``answer`` feeds the answer-keyword check (Layer B-lite); ``chunks`` is the
    ranked retrieval that RetrievalRanking scores (Layer A). Bundling them lets a
    single agent run feed both evaluators instead of running the graph twice.

    Pydantic (not a dataclass) on purpose: the LangSmith seam serializes outputs
    via model_dump and rebuilds them with model_validate (see langsmith_adapter
    _serialize/_deserialize). RetrievedChunk is already pydantic, so the whole
    object — answer + ranked chunks — survives the JSON round-trip intact.
    """

    answer: str | None = None
    chunks: list[RetrievedChunk] = Field(default_factory=list)


def _total_tokens(llm_registry) -> int:
    """Sum total_tokens across all roles in the registry's current counters."""
    return sum(row["total_tokens"] for row in llm_registry.usage_report())


class RAGRetrievalTask:
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
        # Built once and reused — the embedding model is the same for every case.
        self._embedder = Embedder()

    async def run(self, case: RAGRetrievalCase) -> tuple[RAGRetrievalOutput | None, Usage]:
        try:
            if (query := case.query) is None:
                raise Exception("no query passed into ")

            if (chunks := case.max_chunks) is None:
                chunks = 8
                logging.warning("max chunks defaulted to %d", chunks)

            if (kind := case.kind) is None:
                kind = "*"

            # Use the injected registries — the same llm_registry the handler
            # reports on, so its token counters reflect work done here.
            llm_registry = self._deps.llm_registry
            prompt_registry = self._deps.prompt_registry

            # Shared, process-lifetime pool: get_pg_gateway() opens it lazily on
            # first call and returns the same singleton thereafter. The task must
            # NOT open or close it — closing the singleton breaks every later case
            # (the pool can't be reopened). Teardown belongs to process exit.
            pg = get_pg_gateway()

            # Query path is read-only: truncate defaults to False, so a bare repo
            # never touches the pinned corpus. Only the ingestor passes truncate=True.
            repo = CodeIntelRepo(pg)

            graph = build_code_intel_graph(
                embedder=self._embedder,
                repo=repo,
                llm_registry=llm_registry,
                prompt_registry=prompt_registry,
                k=chunks,
            )

            state = CodeIntelState(
                query=query,
                kind=kind,
            )

            # Per-sample usage is the registry delta across this invocation;
            # the registry keeps accumulating so the handler's end-of-run
            # report stays a correct session total.
            before = _total_tokens(llm_registry)
            result: CodeIntelState = await graph.ainvoke(state)
            answer: str | None = result.get("answer")
            # chunks are RetrievedChunk objects written by the retrieve node, in
            # descending score order — exactly the ranked list Layer A scores.
            chunks: list[RetrievedChunk] = list(result.get("chunks") or [])

            output = RAGRetrievalOutput(answer=answer, chunks=chunks)
            return output, Usage(total_tokens=_total_tokens(llm_registry) - before)

        except Exception as e:
            logging.error(e)
            return None, Usage()


