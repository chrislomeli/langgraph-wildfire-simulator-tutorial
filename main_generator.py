"""main_generator.py — the world-service entry point.

Stands up a bootstrapped scenario, ticks it forward, and emits a
location-only change event per tick. The event sink (`call_advisory`)
is stubbed: it dumps the payload for now.

Flow (see [[pod-architecture]]):

    1. bootstrap working copy from seed
    2. start_world_service → engine (WorldView + state_snapshot_log)
    3. iter_tick_events → one TickChangeEvent per tick
    4. call_advisory(event) → stub sink (dump payload)

Next step (deferred): call_advisory becomes a DB-mediated handoff to the
advisory-service. The world-service writes state_snapshot_log back to the
working-copy cell_state rows; advisory-service (a separate pod) reads that
ground truth and decides. They will not share memory.

Run from the project root::

    python main_generator.py
"""

from __future__ import annotations

import logging

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


def call_advisory(event: TickChangeEvent) -> None:
    """Event sink. Stub: dump the payload.

    Later this becomes the handoff to advisory-service. Today it just
    proves the world-service is emitting the right notifications.
    """
    print(
        f"[advisory] tick={event.tick:>3}  "
        f"changed={len(event.changed_cells):>4} cells  "
        f"{event.changed_cells if len(event.changed_cells) <= 8 else str(event.changed_cells[:8]) + ' …'}"
    )


def main() -> None:
    data_store = get_postgres_data_store()
    try:
        engine = start_world_service(
            region_name=REGION,
            version=VERSION,
            data_store=data_store,
            bootstrap=True,  # copy seed → working copy, then run
        )

        logger.info(
            "world-service running: region=%r version=%r grid=%dx%d horizon=%d",
            REGION,
            VERSION,
            engine.rows,
            engine.cols,
            HORIZON_TICKS,
        )

        updated = 0
        for event in iter_tick_events(engine, horizon_ticks=HORIZON_TICKS):
            call_advisory(event)

            # Writeback: keep the DB working copy current as we tick. Only the
            # cells that changed this tick are written (current state, no
            # history — cell_state has no tick column). This is what the
            # advisory-service reads as ground truth once it's a separate pod.
            if event.changed_cells:
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
                    region=REGION, version=VERSION, snapshots=snapshots
                )

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
    main()
