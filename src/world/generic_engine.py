"""
world-simiulator.world.generic_engine

GenericWorldEngine — the domain-agnostic simulation tick loop.

What this does
──────────────
The GenericWorldEngine is the central coordinator.  Each tick:

  1. Environment evolves (tick on EnvironmentState).
  2. Physics module runs (computes StateEvents for cell changes).
  3. StateEvents are applied to the grid.
  4. Ground truth snapshot is recorded.

The engine does NOT:
  - Know what domain it's simulating (fire, ocean, disease, etc.).
  - Interpret cell states or environment values.
  - Know about Kafka, LangGraph, or agents.
  - Publish events to any bus directly — see ``tick_events.iter_tick_events``
    for the locations-only notification stream.

Consumers (the advisory-service) read the world through the WorldView
Protocol the engine implements; they never reach into ``engine.grid``.
See [[pod-architecture]].

Ground truth
────────────
After every tick, the engine records a GenericGroundTruthSnapshot:
  - Environment conditions at that tick
  - What state changes happened (as dicts)
  - A domain-specific summary from the physics module

This is the "answer key" for evaluating agent decisions.
The agent never sees ground truth — it only sees sensor readings.

Reproducibility
───────────────
Set a random seed before running the engine for deterministic results.
This is essential for comparing agent configurations and regression testing.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Generic

from pydantic import BaseModel

from world.cell_state import C
from world.environment import EnvironmentState
from world.generic_grid import GenericTerrainGrid
from world.physics import PhysicsModule, StateEvent
from world.state_snapshot import CellStateSnapshot

logger = logging.getLogger(__name__)


# ── Ground truth snapshot ────────────────────────────────────────────────────
class ShallowCell(BaseModel):
    row: int
    col: int
    layer: int
    attributes: dict
    terrain: str
    fuel_moisture: float


@dataclass
class GenericGroundTruthSnapshot:
    """
    What was actually happening in the world at a given tick.

    Used after the scenario for evaluation: comparing what the agent
    decided to what was actually happening.

    tick            : which simulation tick this snapshot is from
    environment     : environment conditions at this tick (from to_dict())
    state_events    : what changed this tick (serialised StateEvents)
    domain_summary  : domain-specific summary from physics.summarize()
    grid_summary    : cell counts by summary_label (e.g. {"BURNING": 5})
    resource_summary: optional resource readiness data, populated by the
                      scenario script or orchestrator (not by the engine).
                      Empty dict when no ResourceInventory is used.
    """

    tick: int
    environment: dict[str, Any]
    state_events: list[dict[str, Any]]
    domain_summary: dict[str, Any]
    grid_summary: dict[str, int]
    resource_summary: dict[str, Any] = field(default_factory=dict)


# ── Generic world engine ─────────────────────────────────────────────────────


class GenericWorldEngine(Generic[C]):
    """
    Domain-agnostic simulation coordinator.

    Composes a grid, environment, and physics module.  Runs the
    tick loop and records ground truth.  Never interprets domain-
    specific state.

    Usage
    ─────
      from world-simiulator.domains.wildfire.cell_state import FireCellState
      from world-simiulator.domains.wildfire.environment import FireEnvironmentState
      from world-simiulator.domains.wildfire.physics import FirePhysicsModule

      physics = FirePhysicsModule()
      environment = FireEnvironmentState(temperature_c=35, ...)
      grid = GenericTerrainGrid(rows=10, cols=10,
                                initial_state_factory=physics.initial_cell_state)

      engine = GenericWorldEngine(grid=grid, environment=environment, physics=physics)
      for _ in range(60):
          snapshot = engine.tick()
          print(snapshot.domain_summary)
    """

    def __init__(
        self,
        *,
        grid: GenericTerrainGrid[C],
        environment: EnvironmentState,
        physics: PhysicsModule[C],
    ) -> None:
        """
        Parameters
        ──────────
        grid        : the terrain grid (cells with typed domain state)
        environment : the starting environment conditions
        physics     : the pluggable physics module

        The engine takes ownership of grid and environment — it will
        mutate them on each tick.
        """
        self.grid = grid
        self.environment = environment
        self.physics = physics

        # Current simulation tick.  Starts at 0, incremented after each tick().
        self._tick: int = 0
        self.start_date = date.today()

        # History of ground truth snapshots, one per tick.
        self.history: list[GenericGroundTruthSnapshot] = []

        # Per-cell state snapshots accumulated across ticks. Each entry is
        # ready for a direct UPDATE against cell_state. See
        # ``world.state_snapshot`` for the writeback contract.
        self.state_snapshot_log: list[CellStateSnapshot] = []

    @property
    def current_tick(self) -> int:
        """The current simulation tick (0-based, incremented after each tick)."""
        return self._tick

    def set_tick(self, tick: int) -> None:
        """Set the current tick without running physics.

        Used when an engine is reconstructed from a persisted working copy —
        e.g. the advisory-service loads the DB grid (already advanced to some
        tick by the world-service) and must tell the engine which tick that
        grid represents so tick-relative computations (create_forecast /
        create_history) line up. This does NOT advance or mutate the grid; the
        loaded state is taken as-is.
        """
        self._tick = tick

    # ── WorldView Protocol implementation ────────────────────────────
    # The engine exposes a minimal read surface that agent code depends on
    # via the ``WorldView`` Protocol. Keeping these as properties / forwarding
    # methods means agent code never has to reach into ``engine.grid`` or
    # ``engine.physics`` directly.

    @property
    def rows(self) -> int:
        return self.grid.rows

    @property
    def cols(self) -> int:
        return self.grid.cols

    @property
    def cell_size_ft(self) -> float:
        return getattr(self.physics, "cell_size_ft", 200.0)

    def get_cell(self, row: int, col: int, layer: int = 0):
        try:
            return self.grid.get_cell(row, col, layer)
        except Exception:
            return None

    def get_sector(self, cells: list[tuple[int, int]]):
        sector = [cell for row, col in cells if (cell := self.get_cell(row, col, 0))]
        return sector

    def expand_sectors(
        self,
        centers: list[tuple[int, int]],
        radius: int = 1,
    ) -> dict[tuple[int, int], list[tuple[int, int]]]:
        """Expand changed-cell coordinates into merged, in-bounds sectors.

        Each center grows into a (2*radius+1) square halo clamped to the grid.
        Halos that share any cell are merged into one connected region, so no
        cell is ever evaluated twice. Returns one sorted, deduped coordinate
        list per region (coordinates only — callers resolve them via get_sector).
        """
        halos: dict[tuple[int, int], list[tuple[int, int]]] = {}
        for center_row, center_col in centers:
            halo = {
                (row, col)
                for row in range(center_row - radius, center_row + radius + 1)
                for col in range(center_col - radius, center_col + radius + 1)
                if 0 <= row < self.rows and 0 <= col < self.cols
            }
            if halo:
                halos[(center_row, center_col)] = list(halo)
        return halos

        # todo - overlap is not working and messes up centers
        # merged: dict[tuple[int, int], set[tuple[int, int]]] = {}
        # for halo in halos:
        #     overlapping = [region for region in merged if region & halo]
        #     for region in overlapping:
        #         merged.remove(region)
        #         halo |= region
        #     merged.append(halo)
        #
        # return [sorted(region) for region in merged]

    def get_bounding(self):
        return self.rows, self.cols

    # ── Spread-risk summary ───────────────────────────────────────────────────

    @staticmethod
    def degrees_to_compass(degrees: float) -> str:
        """Convert a 0–360 degree bearing to the nearest 8-point compass label."""
        labels = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        return labels[round(degrees / 45) % 8]

    @staticmethod
    def _bearing(dr: int, dc: int) -> float:
        """Compass bearing in degrees from anchor to neighbor (N=0, clockwise)."""
        angle = math.degrees(math.atan2(dc, -dr))
        return (angle + 360) % 360

    @staticmethod
    def _octant(dr: int, dc: int) -> str:
        octants = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        bearing = GenericWorldEngine._bearing(dr, dc)
        return octants[round(bearing / 45) % 8]

    @staticmethod
    def _wind_alignment(bearing_deg: float, wind_direction_deg: float) -> float:
        """1.0 = fully downwind, 0.0 = fully upwind."""
        wind_to = (wind_direction_deg + 180) % 360
        diff = abs(bearing_deg - wind_to) % 360
        diff = min(diff, 360 - diff)
        return (math.cos(math.radians(diff)) + 1) / 2

    @staticmethod
    def _cell_spread_risk(state, bearing_deg: float) -> float:
        """
        Single-cell ignition risk score (0.0–1.0) for an UNBURNED neighbour.

        Combines fuel load, moisture, slope, and wind alignment.
        Returns 0.0 for BURNING or BURNED cells — they are not ignition candidates.
        Requires a FireCellState; returns 0.0 for any other cell type.
        """
        from world.domains.wildfire import FireCellState
        from world.grid import FireState

        if not isinstance(state, FireCellState):
            return 0.0
        if state.fire_state != FireState.UNBURNED:
            return 0.0
        veg = max(0.0, min(1.0, state.vegetation))
        moisture = max(0.0, min(1.0, state.fuel_moisture))
        base = veg * (1 - moisture)
        slope_factor = max(0.1, 1 + (0.1 * state.slope))
        wind = GenericWorldEngine._wind_alignment(bearing_deg, state.wind_direction_deg)
        return round(base * slope_factor * wind, 3)

    def get_spread_risk_summary(self, anchor_row: int, anchor_col: int, radius: int = 5) -> dict:
        """
        Summarise fire-spread risk in each compass direction around an anchor cell.

        Returns a dict keyed by direction (N, NE, E, SE, S, SW, W, NW).
        Each entry: {"cell_count": int, "avg_risk": float, "max_risk": float}

        Risk is derived from vegetation, fuel moisture, slope, and wind alignment.
        Only UNBURNED neighbours contribute; BURNING/BURNED cells score 0.0 because
        the question is where fire might START next, not where it already is.
        Intended as prompt context — include in the agent briefing, not as a tool call.
        """
        buckets: dict[str, list[float]] = defaultdict(list)

        for r in range(anchor_row - radius, anchor_row + radius + 1):
            for c in range(anchor_col - radius, anchor_col + radius + 1):
                if r == anchor_row and c == anchor_col:
                    continue
                cell = self.get_cell(r, c, 0)
                if cell is None:
                    continue
                dr, dc = r - anchor_row, c - anchor_col
                bearing = self._bearing(dr, dc)
                direction = self._octant(dr, dc)
                risk = self._cell_spread_risk(cell.cell_state, bearing)
                buckets[direction].append(risk)

        anchor = self.get_cell(anchor_row, anchor_col, 0)
        wind_deg = getattr(anchor.cell_state, "wind_direction_deg", 0.0) if anchor else 0.0
        wind_speed = getattr(anchor.cell_state, "wind_speed_mps", 0.0) if anchor else 0.0
        summary: dict = {
            "wind_from_degrees": wind_deg,
            "wind_from_compass": self.degrees_to_compass(wind_deg),
            "wind_speed_mps": wind_speed,
        }

        directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        for direction in directions:
            risks = buckets.get(direction, [])
            if not risks:
                summary[direction] = {
                    "cell_count": 0,
                    "avg_risk": 0.0,
                    "max_risk": 0.0,
                    "risk_level": "MINIMAL",
                }
            else:
                avg = round(sum(risks) / len(risks), 3)
                mx = round(max(risks), 3)
                avg_label = self._risk_label(avg)
                max_label = self._risk_label(mx)
                risk_level = avg_label if avg_label == max_label else f"{avg_label}-{max_label}"
                summary[direction] = {
                    "cell_count": len(risks),
                    "avg_risk": avg,
                    "max_risk": mx,
                    "risk_level": risk_level,
                }
        return summary

    @staticmethod
    def _risk_label(score: float) -> str:
        if score >= 0.7:
            return "HIGH"
        if score >= 0.4:
            return "MEDIUM"
        if score >= 0.1:
            return "LOW"
        return "MINIMAL"

    # ── Forecast ─────────────────────────────────────────────────────────────

    @staticmethod
    def _interpolate_segment(segment, tick: int, baseline: float) -> float:
        start_val = segment.start_value if segment.start_value is not None else baseline
        if tick <= segment.start_tick:
            return start_val
        elapsed = tick - segment.start_tick
        if elapsed >= segment.duration_ticks:
            return segment.target_value if segment.hold_after else start_val
        return start_val + (segment.target_value - start_val) * (elapsed / segment.duration_ticks)

    @staticmethod
    def _resolve_metric(metric: str, tick: int, plan: list, baseline: float) -> float:
        segments = [s for s in plan if s.metric == metric]
        if not segments:
            return baseline
        # use the latest segment whose start_tick <= tick
        applicable = [s for s in segments if tick >= s.start_tick]
        if not applicable:
            return baseline
        seg = max(applicable, key=lambda s: s.start_tick)
        return GenericWorldEngine._interpolate_segment(seg, tick, baseline)

    def calculate_forecast(
        self, fire_cell, plan: list, starting_tick: int = 0, periods: int = 10
    ) -> dict:
        """
        Build a NWS-style weather forecast by applying scripted plan segments to a cell baseline.

        Each period represents one simulation tick (one day). Values for metrics
        covered by a ScenarioPlanSegment are linearly interpolated from the segment;
        everything else holds at the fire_cell baseline.

        wind_speed_mps is converted to mph. wind_direction_deg is converted to a
        compass label. precipitation (0–1) is expressed as a 0–100 percent.
        """
        from datetime import date, timedelta

        today = date.today()

        forecast_periods = []
        for i in range(periods):
            tick = starting_tick + i
            day = today + timedelta(days=i)

            temp = self._resolve_metric("temperature_c", tick, plan, fire_cell.temperature_c)
            precip = self._resolve_metric("precipitation", tick, plan, fire_cell.precipitation)
            wind_speed = self._resolve_metric(
                "wind_speed_mps", tick, plan, fire_cell.wind_speed_mps
            )
            wind_dir = self._resolve_metric(
                "wind_direction_deg", tick, plan, fire_cell.wind_direction_deg
            )
            humidity = self._resolve_metric("humidity_pct", tick, plan, fire_cell.humidity_pct)
            fuel_moisture = self._resolve_metric(
                "fuel_moisture", tick, plan, fire_cell.fuel_moisture
            )

            forecast_periods.append(
                {
                    "number": i + 1,
                    "date": day.isoformat(),
                    "temperature": round(temp, 1),
                    "temperatureUnit": "C",
                    "probabilityOfPrecipitation": {
                        "unitCode": "wmoUnit:percent",
                        "value": round(precip * 100, 1),
                    },
                    "windSpeed": f"{round(wind_speed * 2.237)} mph",
                    "windDirection": self.degrees_to_compass(wind_dir),
                    "humidity_pct": round(humidity, 1),
                    "fuel_moisture": round(fuel_moisture, 3),
                }
            )

        return {
            "units": "us",
            "forecastGenerator": "BaselineForecastGenerator",
            "generatedAt": date.today().isoformat(),
            "periods": forecast_periods,
        }

    def calculate_history(self, fire_cell, plan: list) -> dict:
        """
        Build a NWS-style history from tick 0 to current_tick using the same
        plan interpolation as calculate_forecast, run in reverse.

        Tick 0 maps to (today - current_tick days); current_tick maps to today.
        Returns an empty periods list when current_tick is 0 (no history yet).
        """
        today = self.start_date

        periods = 4
        history_periods = []
        simulation_date = self.start_date + timedelta(days=self.current_tick)

        for count_down in range(periods, 0, -1):
            historical_date = simulation_date - timedelta(days=count_down)
            t = self.current_tick - count_down
            plan_tick = max(0, t)

            # if the tick is negative we are going back further than we have data for to get to 'periods' value
            # in that case we use the first valid tick and repeat it
            temp = self._resolve_metric("temperature_c", plan_tick, plan, fire_cell.temperature_c)
            precip = self._resolve_metric("precipitation", plan_tick, plan, fire_cell.precipitation)
            wind_speed = self._resolve_metric(
                "wind_speed_mps", plan_tick, plan, fire_cell.wind_speed_mps
            )
            wind_dir = self._resolve_metric(
                "wind_direction_deg", plan_tick, plan, fire_cell.wind_direction_deg
            )
            humidity = self._resolve_metric("humidity_pct", plan_tick, plan, fire_cell.humidity_pct)
            fuel_moisture = self._resolve_metric(
                "fuel_moisture", plan_tick, plan, fire_cell.fuel_moisture
            )
            rain = f"{precip * 0.15} inches  per hour " if precip > 0.5 else "no rain"

            history_periods.append(
                {
                    "number": t,
                    "date": historical_date.isoformat(),
                    "temperature": round(temp, 1),
                    "temperatureUnit": "C",
                    "precipitation": rain,
                    "windSpeed": f"{round(wind_speed * 2.237)} mph",
                    "windDirection": self.degrees_to_compass(wind_dir),
                    "humidity_pct": round(humidity, 1),
                    "fuel_moisture": round(fuel_moisture, 3),
                }
            )

        return {
            "units": "us",
            "forecastGenerator": "BaselineForecastGenerator",
            "generatedAt": today.isoformat(),
            "periods": history_periods,
        }

    def _baseline_cell(self, row: int, col: int, layer: int = 0):
        """Baseline for forecast/history = the cell's real current state.

        Reads the grid cell (the DB working-copy values loaded at startup), the
        same source ``get_spread_risk_summary`` uses — NOT ``initial_cell_state``,
        which returns a generic default. The plan still overrides any metric it
        covers; this only sets the anchor for un-planned metrics and for plan
        segments whose ``start_value`` is None. Falls back to the physics default
        if the cell isn't on the grid.
        """
        cell = self.get_cell(row, col, layer)
        return (
            cell.cell_state
            if cell is not None
            else self.physics.initial_cell_state(row, col, layer)
        )

    def create_forecast(self, row: int, col: int) -> dict:
        fire_cell = self._baseline_cell(row, col)
        plan = self.physics.get_plan(row, col)
        return self.calculate_forecast(
            fire_cell=fire_cell, plan=plan, starting_tick=self.current_tick
        )

    def create_history(self, row: int, col: int) -> dict:
        fire_cell = self._baseline_cell(row, col)
        plan = self.physics.get_plan(row, col)
        return self.calculate_history(fire_cell=fire_cell, plan=plan)

    def create_briefing(self, row: int, col: int) -> dict:
        fire_cell = self._baseline_cell(row, col)
        plan = self.physics.get_plan(row, col)
        return {
            "history": self.calculate_history(fire_cell=fire_cell, plan=plan),
            "forecast": self.calculate_forecast(
                fire_cell=fire_cell, plan=plan, starting_tick=self.current_tick + 1
            ),
        }

    def tick(self) -> GenericGroundTruthSnapshot:
        """
        Advance the simulation by one step.

        Order of operations:
          1. Environment evolves
          2. Physics module computes state events
          3. State events are applied to the grid
          4. Ground truth snapshot is recorded
          5. Tick counter advances

        Returns the ground truth snapshot for this tick.
        """
        # ── 1. Evolve environment ─────────────────────────────────
        self.environment.tick()

        # ── 2. Compute state changes ─────────────────────────────
        state_events: list[StateEvent[C]] = self.physics.tick_physics(
            grid=self.grid,
            environment=self.environment,
            tick=self._tick,
        )

        # ── 3. Apply state events to the grid ────────────────────
        for event in state_events:
            self.grid.update_cell_state(event.row, event.col, event.new_state, event.layer)

        # ── 4. Record ground truth ───────────────────────────────
        domain_summary = self.physics.summarize(self.grid)
        grid_summary = self.grid.summary_counts()

        snapshot = GenericGroundTruthSnapshot(
            tick=self._tick,
            environment=self.environment.to_dict(),
            state_events=[
                {
                    "row": e.row,
                    "col": e.col,
                    "layer": e.layer,
                    "new_state": e.new_state.model_dump(),
                }
                for e in state_events
            ],
            domain_summary=domain_summary,
            grid_summary=grid_summary,
        )
        self.history.append(snapshot)

        # Per-cell snapshot — full state, every cell, every tick. Captures
        # changes made in-place (e.g. ScriptedTrendPhysics) that don't surface
        # as StateEvents in ``state_events`` above.
        for cell in self.grid.iter_cells():
            self.state_snapshot_log.append(
                CellStateSnapshot(
                    tick=self._tick,
                    grid_row=cell.row,
                    grid_column=cell.col,
                    layer=cell.layer,
                    state=cell.cell_state.model_dump(),
                )
            )

        # Log a summary line for visibility during demos.
        logger.info(
            "Tick %03d | %s | events=%d",
            self._tick,
            " ".join(f"{k}={v}" for k, v in grid_summary.items()),
            len(state_events),
        )

        # ── 5. Advance tick ──────────────────────────────────────
        self._tick += 1

        return snapshot

    def run(self, ticks: int) -> list[GenericGroundTruthSnapshot]:
        """
        Run the simulation for a fixed number of ticks.

        Convenience method for scenarios that run to completion
        rather than being driven tick-by-tick.
        """
        return [self.tick() for _ in range(ticks)]

    def get_snapshot(self, tick: int) -> GenericGroundTruthSnapshot | None:
        """
        Retrieve the ground truth snapshot for a specific tick.

        Returns None if the tick hasn't been simulated yet.
        """
        if 0 <= tick < len(self.history):
            return self.history[tick]
        return None

    def inject_state(self, row: int, col: int, state: C, layer: int = 0) -> None:
        """
        Manually set a cell's state.

        Used by scenario scripts to set up initial conditions
        (e.g. ignite a cell, place an animal, seed an infection).

        Parameters
        ──────────
        row, col, layer : which cell to modify (layer defaults to 0)
        state           : the new CellState to set
        """
        self.grid.update_cell_state(row, col, state, layer)
        logger.info(
            "Injected state at (%d,%d,%d): %s tick=%d",
            row,
            col,
            layer,
            state.summary_label(),
            self._tick,
        )
