"""Labeled escalation scenarios — the ground truth for the eval harness.

Each Scenario is a hand-built sector (the same `EvaluationCell` shape the
`evaluate` node receives) plus the outcome a human expects. Because the
inputs are authored directly, we know the right answer and can measure
whether the agent agrees.

Scoring knobs per scenario:
  - expect_escalate : True / False to score the binary decision, or None to
                      leave it unscored (genuinely ambiguous cases — score
                      only calibration there).
  - expect_confidence : "high" / "low" to assert the model is appropriately
                        (un)certain, or None to just observe.
  - expect_keywords : substrings that should appear in contributing_factors
                      (e.g. the model should *name* the mitigating factor).
"""

from __future__ import annotations

from dataclasses import dataclass

from agents.commons.schemas import EvaluationCell
from world.domains.wildfire.cell_state import FireCellState
from world.grid import TerrainType


@dataclass(frozen=True)
class Scenario:
    id: str
    description: str
    cells: list[EvaluationCell]
    bounding: tuple[int, int]  # (max_rows, max_columns) — prompt context only
    expect_escalate: bool | None
    expect_confidence: str | None = None  # "high" | "low" | None
    expect_keywords: tuple[str, ...] = ()
    notes: str = ""


def cell(row: int, col: int, **state) -> EvaluationCell:
    """Build one EvaluationCell, overriding only the FireCellState fields you care about."""
    return EvaluationCell(row=row, col=col, layer=0, attributes={}, state=FireCellState(**state))


BOUNDS = (50, 50)


SCENARIOS: list[Scenario] = [
    Scenario(
        id="clear_extreme",
        description="Hot, bone-dry, high wind, dense fuel — textbook high danger.",
        cells=[
            cell(10, 10, temperature_c=45, humidity_pct=8, wind_speed_mps=22,
                 vegetation=0.85, fuel_moisture=0.05),
        ],
        bounding=BOUNDS,
        expect_escalate=True,
        expect_confidence="high",
        notes="Sanity: the agent should escalate confidently.",
    ),
    Scenario(
        id="clear_safe",
        description="Cool, humid, calm, damp fuel — nothing to act on.",
        cells=[
            cell(10, 10, temperature_c=12, humidity_pct=85, wind_speed_mps=2,
                 vegetation=0.6, fuel_moisture=0.7),
        ],
        bounding=BOUNDS,
        expect_escalate=False,
        expect_confidence="high",
        notes="Sanity / false-positive guard.",
    ),
    Scenario(
        id="not_burnable",
        description="Hot and dry air, but bare rock with no vegetation — no fuel, no fire potential.",
        cells=[
            cell(10, 10, terrain_type=TerrainType.ROCK, vegetation=0.0,
                 temperature_c=44, humidity_pct=9, wind_speed_mps=15, fuel_moisture=0.05),
        ],
        bounding=BOUNDS,
        expect_escalate=False,
        expect_confidence="high",
        notes="Tests the burnability rule: scary weather over non-fuel is not a fire risk.",
    ),
    Scenario(
        id="borderline",
        description="Moderate everything, one mild risk factor — genuinely ambiguous.",
        cells=[
            cell(10, 10, temperature_c=33, humidity_pct=16, wind_speed_mps=10,
                 vegetation=0.5, fuel_moisture=0.25),
        ],
        bounding=BOUNDS,
        expect_escalate=None,  # either call is defensible
        expect_confidence="low",
        notes="Calibration: the model should NOT be highly confident on a borderline case.",
    ),
    Scenario(
        id="mixed_signals",
        description="Hot, dry air over recently-soaked fuel — atmosphere says risk, fuel says no.",
        cells=[
            cell(10, 10, temperature_c=40, humidity_pct=12, wind_speed_mps=14,
                 vegetation=0.7, fuel_moisture=0.75),
        ],
        bounding=BOUNDS,
        expect_escalate=False,
        expect_confidence="low",
        expect_keywords=("moisture",),
        notes="Reconciliation: wet fuel should temper the decision AND be named as the reason.",
    ),
    Scenario(
        id="shifting_wind",
        description="Several elevated cells with inconsistent wind directions — direction is ambiguous.",
        cells=[
            cell(10, 10, temperature_c=38, humidity_pct=14, wind_speed_mps=16,
                 vegetation=0.7, fuel_moisture=0.15, wind_direction_deg=10),
            cell(10, 11, temperature_c=38, humidity_pct=14, wind_speed_mps=16,
                 vegetation=0.7, fuel_moisture=0.15, wind_direction_deg=110),
            cell(11, 10, temperature_c=37, humidity_pct=15, wind_speed_mps=15,
                 vegetation=0.7, fuel_moisture=0.18, wind_direction_deg=250),
        ],
        bounding=BOUNDS,
        expect_escalate=True,
        expect_confidence=None,  # observe — see note
        notes=(
            "Your shifting-wind case, authored deterministically. Conditions are "
            "dangerous so it should escalate; confidence behavior under directional "
            "ambiguity is the thing to watch (and becomes a real assertion once a "
            "forecast/spread tool exists)."
        ),
    ),
]
