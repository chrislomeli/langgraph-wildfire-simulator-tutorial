"""main_generator.py — the world-service entry point.

Stands up a bootstrapped scenario, ticks it forward, writes each tick's
changed cells back to the DB working copy, and hands the changed cells to
the advisory controller.

Flow (see [[pod-architecture]]):

    1. bootstrap working copy from seed
    2. start_world_service → engine (WorldView + state_snapshot_log)
    3. iter_tick_events → one TickChangeEvent per tick
    4. writeback changed cells to the DB working copy
    5. call_advisory(event) → AdvisoryController.handle (in-process, for dev)

The writeback happens BEFORE the advisory call so the advisory controller —
which re-reads the world from the DB — sees this tick's grid, not the prior
tick's.

In-process vs. pods: today ``call_advisory`` calls the controller directly so
the full sensor→risk→advisory pipeline runs end to end in one process. In
production this becomes a DB-mediated handoff to a separate advisory pod: the
world-service writes ``cell_state`` and emits a locations-only event; the
advisory pod reads that ground truth and decides. They will not share memory —
only the DB and the event payload.

Run from the project root::

    python main_generator.py
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import uuid

from controllers.main_advisor import AdvisoryController
from controllers.schemas import AdvisoryRequest
from logging_config import configure_logging

configure_logging(level=logging.INFO)

from stores import get_postgres_data_store  # noqa: E402
from world import iter_tick_events  # noqa: E402
from world.state_snapshot import CellStateSnapshot  # noqa: E402
from world.tick_events import TickChangeEvent  # noqa: E402
from world.domains.wildfire.scenario_loader import start_world_service  # noqa: E402

logger = logging.getLogger(__name__)

REGION = "lpnf-south"
VERSION = "simulation"
HORIZON_TICKS = 30


async def call_advisory(
    controller: AdvisoryController,
    region: str,
    version: str,
    event: TickChangeEvent,
) -> None:
    """Hand this tick's changed cells to the advisory controller (in-process).

    Builds the same ``AdvisoryRequest`` the wire payload would carry and runs it
    through the shared controller. In production this is replaced by a
    DB-mediated handoff to a separate advisory pod; here we call ``handle``
    directly so the whole pipeline runs end to end.
    """
    cells = [dict(row=r, col=c, layer=layer) for (r, c, layer) in event.changed_cells]
    request = AdvisoryRequest.model_validate(
        dict(
            id=str(uuid.uuid4()),
            region=region,
            version=version,
            tick=event.tick,
            timestamp=datetime.datetime.now().isoformat(),
            cells=cells,
        )
    )
    result = await controller.handle(request)
    print(result.model_dump_json(indent=2))


async def generate_world_events(region: str, version: str, horizon_ticks: int) -> None:
    data_store = get_postgres_data_store()
    try:
        engine = start_world_service(
            region_name=region,
            version=version,
            data_store=data_store,
            bootstrap=True,  # copy seed → working copy, then run
        )

        # One controller, reused across every tick — its DB pool (the shared
        # data_store) and LLM/prompt registries are built once, not per tick.
        controller = AdvisoryController(data_store)

        logger.info(
            "world-service running: region=%r version=%r grid=%dx%d horizon=%d",
            region,
            version,
            engine.rows,
            engine.cols,
            horizon_ticks,
        )

        updated = 0
        for event in iter_tick_events(engine, horizon_ticks=horizon_ticks):
            print(f"\nTICK {event.tick}")

            if not event.changed_cells:
                continue

            # Writeback FIRST: keep the DB working copy current so the advisory
            # controller (which re-reads the world from the DB) sees this tick's
            # grid. Only the cells that changed this tick are written (current
            # state, no history — cell_state has no tick column).
            snapshots = [
                CellStateSnapshot(
                    tick=event.tick,
                    grid_row=r,
                    grid_column=c,
                    layer=layer,
                    state=engine.get_cell(r, c, layer).cell_state.model_dump(),
                )
                for (r, c, layer) in event.changed_cells
            ]
            updated += data_store.cell_state.write_state(
                region=region, version=version, snapshots=snapshots
            )

            # Then notify the advisory-service for the cells that changed.
            await call_advisory(controller, region, version, event)

        logger.info(
            "world-service done: %d snapshots in log, %d cell-writes to DB",
            len(engine.state_snapshot_log),
            updated,
        )
    finally:
        # Drain the connection pool so its worker threads shut down cleanly
        # instead of timing out on interpreter exit.
        data_store.close()


if __name__ == "__main__":
    asyncio.run(generate_world_events(region=REGION, version=VERSION, horizon_ticks=HORIZON_TICKS))
