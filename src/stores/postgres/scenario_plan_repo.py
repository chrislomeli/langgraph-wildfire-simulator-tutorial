"""Scenario plan repository — loads scripted per-cell weather ramps from DB."""

from __future__ import annotations

import logging

from stores.base import ScenarioPlanRepository as ScenarioPlanRepositoryBase
from stores.postgres.gateway import PgGateway
from stores.schemas import ScenarioPlanSegment

logger = logging.getLogger(__name__)


class ScenarioPlanRepository(ScenarioPlanRepositoryBase):
    """Loads scenario_cell_plan rows, grouped per cell, for ScriptedTrendPhysics.

    Sparse by design: only cells with authored segments appear in the
    result. A cell absent from the returned dict has no scripted trend
    and stays static at its seed value.
    """

    def __init__(self, pg_gateway: PgGateway):
        self._pg = pg_gateway

    def fetch_plan(self, region_name: str) -> dict[tuple[int, int, int], list[ScenarioPlanSegment]]:
        sql = """
        select region,
               grid_row,
               grid_column,
               layer,
               metric,
               start_tick,
               duration_ticks,
               start_value,
               target_value
        from scenario_cell_plan
        where region = %s
        order by grid_row, grid_column, layer, metric, start_tick;
        """
        rows = self._pg.fetch_rows(sql, (region_name,))

        plan: dict[tuple[int, int, int], list[ScenarioPlanSegment]] = {}
        for row in rows:
            seg = ScenarioPlanSegment.model_validate(row)
            key = (seg.grid_row, seg.grid_column, seg.layer)
            plan.setdefault(key, []).append(seg)

        _validate_no_overlap(plan)

        logger.info(
            "Loaded scenario plan for region %r — %d cell(s), %d segment(s)",
            region_name,
            len(plan),
            sum(len(v) for v in plan.values()),
        )
        return plan


def _validate_no_overlap(
    plan: dict[tuple[int, int, int], list[ScenarioPlanSegment]],
) -> None:
    """Raise ValueError if any (cell, metric) has overlapping tick ranges.

    Rows arrive ordered by start_tick, so one forward pass per
    (cell, metric) suffices: each segment must start at or after the
    previous segment's end (start_tick + duration_ticks).
    """
    for (r, c, layer), segments in plan.items():
        end_by_metric: dict[str, tuple[int, int]] = {}
        for seg in segments:
            prev = end_by_metric.get(seg.metric)
            if prev is not None:
                prev_start, prev_end = prev
                if seg.start_tick < prev_end:
                    raise ValueError(
                        f"Overlapping scenario_cell_plan segments for cell "
                        f"({r},{c},{layer}) metric {seg.metric!r}: segment at "
                        f"start_tick={seg.start_tick} overlaps previous segment "
                        f"covering ticks [{prev_start}, {prev_end})."
                    )
            end_by_metric[seg.metric] = (
                seg.start_tick,
                seg.start_tick + seg.duration_ticks,
            )
