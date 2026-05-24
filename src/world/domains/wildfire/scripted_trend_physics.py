"""
world-simiulator.domains.wildfire.scripted_trend_physics

Deterministic, DB-driven weather driver for the ignition-risk app.

Instead of simulating fire propagation (Rothermel), this physics module
moves each cell's weather along *authored ramps* loaded from the
``scenario_cell_plan`` table. No fire is ever ignited or spread — the
agent forecasts ignition risk from the scripted conditions.

Why this exists
───────────────
The app's purpose is ignition-risk advisory + resource pre-positioning,
not fire tracking. Scripted ramps are deterministic and verifiable: the
whole sensor→risk→advisory pipeline can be asserted at a given tick.
Rothermel is retained separately for a future "resource drain from
active burns" capability.

Segment semantics (inclusive end)
─────────────────────────────────
A segment owns ticks ``[start_tick, start_tick + duration_ticks]``:

  - tick < start_tick                       → inactive (metric untouched)
  - start_tick <= tick <= end               → ramping; value reaches
                                               target exactly at ``end``
  - tick > end and hold_after               → held at target_value
  - tick > end and not hold_after           → released; the metric is
                                               left at target (the last
                                               value written, at ``end``)

``start_value = None`` chains: it resolves to the preceding segment's
target for the same (cell, metric), or — if there is no predecessor —
the cell's seed value captured the first tick the segment activates.

In-place mutation is deliberate and mirrors
``RothermelFirePhysicsModule._evolve_cell_weather`` (weather is dense —
every scripted cell, every tick — so no StateEvents). ``tick_physics``
returns ``[]``.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

from world.domains.wildfire.cell_state import FireCellState
from world.generic_grid import GenericTerrainGrid
from world.physics import PhysicsModule, StateEvent

if TYPE_CHECKING:
    from stores.schemas import ScenarioPlanSegment
    from world.domains.wildfire.environment import FireEnvironmentState

# Per-metric physical bounds (match RothermelFirePhysicsModule for parity).
# wind_direction_deg is special-cased (wraps mod 360).
_BOUNDS: dict[str, tuple[float, float]] = {
    "temperature_c": (-10.0, 80.0),
    "humidity_pct": (3.0, 100.0),
    "wind_speed_mps": (0.0, 50.0),
    "pressure_hpa": (950.0, 1060.0),
    "fuel_moisture": (0.0, 1.0),
    "precipitation": (0.0, 1.0),  # 0–1 fraction (engine renders it as precip*100 %)
}
_METRICS = set(_BOUNDS) | {"wind_direction_deg"}


def _curve(name: str, p: float) -> float:
    """Map linear progress p∈[0,1] through a named easing curve."""
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    if name == "ease_in":
        return p * p
    if name == "ease_out":
        return 1.0 - (1.0 - p) ** 2
    if name == "step":
        return 0.0  # p<1 here (p>=1 handled above)
    return p  # linear (schema CHECK guarantees no other value)


class ScriptedTrendPhysics(PhysicsModule[FireCellState]):
    """Drives per-cell weather along authored ramps. Never ignites fire."""

    def __init__(
        self,
        plan: dict[tuple[int, int, int], list[ScenarioPlanSegment]],
        jitter_sigma: float = 0.0,
    ) -> None:
        """
        plan         : {(row, col, layer): [segments]} from ScenarioPlanRepository.
                       Sparse — cells absent here stay static at their seed.
        jitter_sigma : Gaussian noise stddev added per metric per tick.
                       Default 0.0 → exact, testable values.
        """
        self._plan = plan
        self._jitter_sigma = jitter_sigma
        # Resolved start values for start_value=None segments, captured on
        # first activation so a mid-ramp grid read can't feed back.
        self._resolved_start: dict[tuple[int, int, int, str, int], float] = {}
        # Locations the most recent tick_physics() call wrote to. Consumed by
        # iter_tick_events to produce TickChangeEvents. Empty before the first
        # tick; replaced (not appended to) at the start of each tick.
        self.last_changed_cells: set[tuple[int, int, int]] = set()

    def initial_cell_state(self, row: int, col: int, layer: int = 0) -> FireCellState:
        return FireCellState()

    def get_plan(self, row: int, col: int, layer: int = 0):
        # Sparse plan: cells with no authored ramps return [] (they stay static
        # at their seed). Indexing with [] would KeyError on those, crashing
        # create_briefing for any unplanned cell — so use .get with an empty
        # default to match the "absent → static" contract in this module's docs.
        return self._plan.get((row, col, layer), [])

    def _resolve_start(
        self,
        r: int,
        c: int,
        layer: int,
        seg: ScenarioPlanSegment,
        state: FireCellState,
    ) -> float:
        if seg.start_value is not None:
            return seg.start_value

        key = (r, c, layer, seg.metric, seg.start_tick)
        cached = self._resolved_start.get(key)
        if cached is not None:
            return cached

        # Chain from the latest preceding segment for the same metric; its
        # frozen value is its target (target is written at that segment's end).
        prev_start = -1
        prev_target: float | None = None
        for other in self._plan[(r, c, layer)]:
            if (
                other.metric == seg.metric
                and other.start_tick < seg.start_tick
                and other.start_tick > prev_start
            ):
                prev_start = other.start_tick
                prev_target = other.target_value

        resolved = prev_target if prev_target is not None else getattr(state, seg.metric)
        self._resolved_start[key] = resolved
        return resolved

    def _clamp(self, metric: str, value: float) -> float:
        if metric == "wind_direction_deg":
            return value % 360.0
        lo, hi = _BOUNDS[metric]
        return max(lo, min(hi, value))

    def tick_physics(
        self,
        grid: GenericTerrainGrid[FireCellState],
        environment: FireEnvironmentState,
        tick: int,
    ) -> list[StateEvent[FireCellState]]:
        self.last_changed_cells = set()
        for (r, c, layer), segments in self._plan.items():
            cell = grid.get_cell(r, c, layer)
            state = cell.cell_state
            updates: dict[str, float] = {}

            for seg in segments:
                if seg.metric not in _METRICS:
                    continue
                end = seg.start_tick + seg.duration_ticks
                if tick < seg.start_tick:
                    continue
                if tick > end:
                    if not seg.hold_after:
                        continue
                    value = seg.target_value
                else:
                    v0 = self._resolve_start(r, c, layer, seg, state)
                    p = (tick - seg.start_tick) / seg.duration_ticks
                    value = v0 + (seg.target_value - v0) * _curve(seg.curve, p)
                # Non-overlap is validated at load; at a shared boundary tick
                # the later segment (iterated last) deterministically wins.
                updates[seg.metric] = value

            if not updates:
                continue

            if self._jitter_sigma > 0.0:
                for m in list(updates):
                    updates[m] += random.gauss(0.0, self._jitter_sigma)

            for m, v in updates.items():
                updates[m] = round(self._clamp(m, v), 4)

            grid.update_cell_state(r, c, state.model_copy(update=updates), layer)
            self.last_changed_cells.add((r, c, layer))

        return []

    def summarize(self, grid: GenericTerrainGrid[FireCellState]) -> dict[str, Any]:
        temps: list[float] = []
        hums: list[float] = []
        danger = 0
        for r in range(grid.rows):
            for c in range(grid.cols):
                st = grid.get_cell(r, c).cell_state
                temps.append(st.temperature_c)
                hums.append(st.humidity_pct)
                factors = (
                    st.temperature_c > 32,
                    st.humidity_pct < 15,
                    st.vegetation < 0.50,
                    st.wind_speed_mps > 20,
                )
                if sum(factors) >= 2:
                    danger += 1
        n = len(temps) or 1
        return {
            "scripted_cells": len(self._plan),
            "mean_temperature_c": round(sum(temps) / n, 2),
            "mean_humidity_pct": round(sum(hums) / n, 2),
            "danger_cells": danger,
        }
