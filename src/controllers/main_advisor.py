from __future__ import annotations

import asyncio
import logging

from agents.commons import CellReadings, CollatedRecordRisk
from agents.commons.agent_dependencies import AgentDependencies
from agents.commons.schemas import Escalation, Evaluation
from agents.logistics.state import LogisticsAssessment
from agents.supervisor import build_supervisor_graph
from agents.supervisor.state import SupervisorGraph, SupervisorState
from config import get_settings
from controllers.schemas import AdvisoryRequest
from logging_config import configure_logging
from prompts import PromptRegistry
from tools.sectors import make_get_sectors

configure_logging(level=logging.INFO)

from stores import get_postgres_data_store, DataStore  # noqa: E402
from world import GenericCell, GenericWorldEngine  # noqa: E402
from world.domains.wildfire.scenario_loader import start_world_service  # noqa: E402
from llm.llm_registry import LLM_ROLE_CONFIG, build_llm_registry, models  # noqa: E402

logger = logging.getLogger(__name__)

def build_agent_deps(
    engine: GenericWorldEngine,
    data_store: DataStore | None = None,
) -> AgentDependencies:
    """Construct the LLM/prompt/store dependencies for graph compilation."""
    settings = get_settings()
    settings.apply_langsmith()

    llm_registry = build_llm_registry(settings, models, LLM_ROLE_CONFIG)

    store = None

    prompt_registry = PromptRegistry()
    prompt_registry.register_models(CellReadings, Evaluation, LogisticsAssessment)

    return AgentDependencies(
        prompt_registry=prompt_registry,
        llm_registry=llm_registry,
        world_engine=engine,
        store=store,
        data_store=data_store,
    )

async def handle_world_changes(request: AdvisoryRequest) -> None:
    data_store: DataStore | None = None
    try:
        # data
        data_store = get_postgres_data_store()

        # world engin with simulation data
        engine = start_world_service(
            region_name=request.region,
            version=request.version,
            data_store=data_store,
            bootstrap=False,
        )



        # inject dependencies package
        agent_dependencies = build_agent_deps(engine, data_store=data_store)

        # build graph
        supervisor_graph: SupervisorGraph = build_supervisor_graph(agent_dependencies=agent_dependencies)

        # initial state
        initial_state = SupervisorState(updates=request.cells)

        # invoke
        result = await supervisor_graph.ainvoke(initial_state)


        world_cells : list[GenericCell] = []
        for cell in request.cells:
            if data_cell:= engine.get_cell(cell.row, cell.col):
                world_cells.append(data_cell)

        print("done")

    except Exception as e:
        logger.error(e)


    finally:
        # Drain the connection pool so its worker threads shut down cleanly
        # instead of timing out on interpreter exit.
        if data_store is not None:
            data_store.close()


if __name__ == "__main__":
    payload = {
        "id": "6eda4bf8-e486-4573-ad29-f8699d970c5e",
        "region": "lpnf-south",
        "version": "simulation",
        "tick": 29,
        "timestamp": "2026-05-21T04:56:24.118478",
        "cells": [
            {
                "row": 5,
                "col": 5,
                "layer": 0
            },
            {
                "row": 25,
                "col": 25,
                "layer": 0
            }
        ]
    }

    request = AdvisoryRequest.model_validate(payload)
    asyncio.run(handle_world_changes(request))

