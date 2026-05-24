from __future__ import annotations

import asyncio
import logging

from pydantic import BaseModel, Field

from agents.commons.agent_dependencies import AgentDependencies
from agents.commons.schemas import Escalation, Evaluation, EvaluationCell
from agents.logistics.state import LogisticsAssessment
from agents.supervisor import build_supervisor_graph
from agents.supervisor.state import SupervisorGraph, SupervisorState
from config import get_settings
from controllers.schemas import AdvisoryRequest
from logging_config import configure_logging
from prompts import PromptRegistry

configure_logging(level=logging.INFO)

from stores import get_postgres_data_store, DataStore  # noqa: E402
from world import GenericWorldEngine  # noqa: E402
from world.domains.wildfire.scenario_loader import start_world_service  # noqa: E402
from llm.llm_registry import LLM_ROLE_CONFIG, build_llm_registry, models  # noqa: E402

logger = logging.getLogger(__name__)


class AdvisoryResult(BaseModel):
    """Transport-agnostic outcome of one advisory run.

    The controller returns this; the caller — a FastAPI endpoint, or the
    ``__main__`` dev harness — decides how to serialize or print it. Kept small
    and JSON-serialisable so the HTTP layer can stay pure transport.
    """

    escalations: list[Escalation] = Field(default_factory=list)
    situation_summary: str | None = None
    logistics_plan: str | None = None


class AdvisoryController:
    """Advisory-service controller — transport-agnostic.

    Long-lived, expensive dependencies (the ``data_store`` DB pool, the LLM
    registry, the prompt registry) are built once and reused across requests.
    Per-request work — loading the world at the request's tick, compiling the
    supervisor graph, running it — happens in ``handle``.

    Wiring:
      - FastAPI: build one controller in the app lifespan; the endpoint is a
        thin shim that ``await``s ``handle(request)`` and returns the result.
      - Dev / CLI: the ``__main__`` block below builds one and calls ``handle``
        directly — no HTTP layer needed to exercise the pipeline.

    ``data_store`` is injected, not constructed here, so its lifecycle belongs
    to the caller (the endpoint/CLI that created it also closes it).
    """

    def __init__(self, data_store: DataStore) -> None:
        self._data_store = data_store

        settings = get_settings()
        settings.apply_langsmith()

        # Built once — reused for every request this controller serves.
        self._llm_registry = build_llm_registry(settings, models, LLM_ROLE_CONFIG)
        self._prompt_registry = PromptRegistry()
        self._prompt_registry.register_models(
            EvaluationCell, Evaluation, Escalation, LogisticsAssessment
        )

    def _build_deps(self, engine: GenericWorldEngine) -> AgentDependencies:
        """Per-request deps: the shared registries + this request's world engine."""
        return AgentDependencies(
            prompt_registry=self._prompt_registry,
            llm_registry=self._llm_registry,
            world_engine=engine,
            store=None,
            data_store=self._data_store,
        )

    async def handle(self, request: AdvisoryRequest) -> AdvisoryResult:
        """Run the advisory pipeline for one request and return the outcome."""
        # Load the world from the DB working copy (already advanced by the
        # world-service), then align the engine's tick so create_forecast /
        # create_history project from the right point — no re-ticking, the
        # loaded grid is taken as-is.
        engine = start_world_service(
            region_name=request.region,
            version=request.version,
            data_store=self._data_store,
            bootstrap=False,
        )
        engine.set_tick(request.tick)

        deps = self._build_deps(engine)
        supervisor_graph: SupervisorGraph = build_supervisor_graph(agent_dependencies=deps)

        result = await supervisor_graph.ainvoke(SupervisorState(updates=request.cells))

        return AdvisoryResult(
            escalations=result.get("escalations", []),
            situation_summary=result.get("situation_summary"),
            logistics_plan=result.get("logistics_plan"),
        )


async def advisory_service(advisory_request: AdvisoryRequest) -> AdvisoryResult:
    """One-shot convenience wrapper: build a controller for a single request,
    run it, and close the DB pool.

    Kept for callers that just want a single run (e.g. main_generator). For
    repeated calls, build one ``AdvisoryController`` and reuse it so the DB pool
    and registries aren't rebuilt every time.
    """
    data_store = get_postgres_data_store()
    try:
        controller = AdvisoryController(data_store)
        return await controller.handle(advisory_request)
    finally:
        # Drain the connection pool so its worker threads shut down cleanly.
        data_store.close()


if __name__ == "__main__":
    payload = {
        "id": "6eda4bf8-e486-4573-ad29-f8699d970c5e",
        "region": "lpnf-south",
        "version": "simulation",
        "tick": 29,
        "timestamp": "2026-05-21T04:56:24.118478",
        "cells": [
            {"row": 5, "col": 5, "layer": 0},
            {"row": 25, "col": 25, "layer": 0},
        ],
    }
    request = AdvisoryRequest.model_validate(payload)

    async def _main() -> None:
        # Dev harness — exercise the controller directly, no HTTP layer.
        data_store = get_postgres_data_store()
        controller = AdvisoryController(data_store)
        try:
            result = await controller.handle(request)
            print(result.model_dump_json(indent=2))
        finally:
            data_store.close()

    asyncio.run(_main())
