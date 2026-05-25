"""evals.escalation.cases — self-contained golden cases for the escalation eval.

Each EscalationCase carries everything the evaluate node LLM path needs:
  - cell         : EvaluationCell (the human-prompt reading)
  - scenario_text: pre-authored radial sector summary (no hotspot_sectors() needed)
  - forecast     : pre-authored weather forecast periods (no create_briefing() needed)
  - history      : pre-authored weather history periods

Pydantic model so LangSmith can round-trip it through seed_dataset /
make_target without a custom serializer.

Authored directly so we know the right answer and can craft scenarios that
would be impossible or unreliable to generate from a synthetic world engine
(e.g. urban settlement in the spread path, conflicting wind directions).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from agents.commons.schemas import EvaluationCell
from world.domains.wildfire.cell_state import FireCellState
from world.grid import TerrainType


class EscalationCase(BaseModel):
    id: str
    description: str
    cell: EvaluationCell
    scenario_text: str
    forecast: list[dict]
    history: list[dict]
    max_rows: int = 50
    max_cols: int = 50
    expect_escalate: bool | None = None
    expect_confidence: str | None = None  # "high" | "low" | None = observe only
    expect_keywords: tuple[str, ...] = ()
    notes: str = ""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cell(row: int, col: int, **state_kwargs) -> EvaluationCell:
    return EvaluationCell(row=row, col=col, layer=0, attributes={}, state=FireCellState(**state_kwargs))


def _forecast(temp: float, humidity: float, wind_mps: float, wind_dir: str,
              fuel_moisture: float, precip_pct: float = 0.0) -> list[dict]:
    """4-period NWS-style forecast, steady conditions."""
    dates = ["2026-05-25", "2026-05-26", "2026-05-27", "2026-05-28"]
    return [
        {
            "number": i + 1,
            "date": d,
            "temperature": round(temp + (i * 0.5), 1),
            "temperatureUnit": "C",
            "probabilityOfPrecipitation": {"unitCode": "wmoUnit:percent", "value": precip_pct},
            "windSpeed": f"{round(wind_mps * 2.237)} mph",
            "windDirection": wind_dir,
            "humidity_pct": round(humidity - (i * 0.5), 1),
            "fuel_moisture": round(fuel_moisture, 3),
        }
        for i, d in enumerate(dates)
    ]


def _history(temp: float, humidity: float, wind_mps: float, wind_dir: str,
             fuel_moisture: float, rain: str = "no rain") -> list[dict]:
    """4-period NWS-style history going back 4 days."""
    dates = ["2026-05-20", "2026-05-21", "2026-05-22", "2026-05-23"]
    return [
        {
            "number": -(4 - i),
            "date": d,
            "temperature": round(temp - (0.5 * (3 - i)), 1),
            "temperatureUnit": "C",
            "precipitation": rain,
            "windSpeed": f"{round(wind_mps * 2.237)} mph",
            "windDirection": wind_dir,
            "humidity_pct": round(humidity + (0.5 * (3 - i)), 1),
            "fuel_moisture": round(fuel_moisture, 3),
        }
        for i, d in enumerate(dates)
    ]


# ── Cases ─────────────────────────────────────────────────────────────────────

CASES: list[EscalationCase] = [

    EscalationCase(
        id="clear_extreme",
        description="Hot, bone-dry, high wind, dense cured fuel — textbook high danger.",
        cell=_cell(
            10, 10,
            temperature_c=45.0,
            humidity_pct=8.0,
            wind_speed_mps=22.0,
            wind_direction_deg=225.0,
            vegetation=0.85,
            fuel_moisture=0.05,
        ),
        scenario_text=(
            "Hotspot at (10, 10): Risk=9/10, Confidence=3/3\n"
            "Radial sector analysis:\n"
            "  N : 1.0mi → fuel continues beyond trace limit | fuel=0.83 | moisture=0.05 | slope=0.0° | fire_intensity=0.00\n"
            "  NE: 1.0mi → fuel continues beyond trace limit | fuel=0.85 | moisture=0.05 | slope=0.0° | fire_intensity=0.00 \U0001f525 WIND-ALIGNED\n"
            "  E : 1.0mi → fuel continues beyond trace limit | fuel=0.82 | moisture=0.05 | slope=0.0° | fire_intensity=0.00\n"
            "  SE: 1.0mi → fuel continues beyond trace limit | fuel=0.84 | moisture=0.05 | slope=0.0° | fire_intensity=0.00\n"
            "  S : 1.0mi → fuel continues beyond trace limit | fuel=0.81 | moisture=0.06 | slope=0.0° | fire_intensity=0.00\n"
            "  SW: 1.0mi → fuel continues beyond trace limit | fuel=0.83 | moisture=0.06 | slope=0.0° | fire_intensity=0.00\n"
            "  W : 1.0mi → fuel continues beyond trace limit | fuel=0.80 | moisture=0.06 | slope=0.0° | fire_intensity=0.00\n"
            "  NW: 1.0mi → fuel continues beyond trace limit | fuel=0.82 | moisture=0.05 | slope=0.0° | fire_intensity=0.00"
        ),
        forecast=_forecast(46.0, 7.0, 23.0, "SW", 0.04),
        history=_history(42.0, 10.0, 20.0, "SW", 0.07),
        expect_escalate=True,
        expect_confidence="high",
        notes="Sanity: all major danger factors elevated. Model should escalate confidently.",
    ),

    EscalationCase(
        id="clear_safe",
        description="Cool, humid, calm wind, damp fuel — nothing to act on.",
        cell=_cell(
            10, 10,
            temperature_c=12.0,
            humidity_pct=85.0,
            wind_speed_mps=2.0,
            wind_direction_deg=90.0,
            vegetation=0.6,
            fuel_moisture=0.70,
        ),
        scenario_text=(
            "Hotspot at (10, 10): Risk=1/10, Confidence=3/3\n"
            "Radial sector analysis:\n"
            "  N : 1.0mi → fuel continues beyond trace limit | fuel=0.58 | moisture=0.69 | slope=0.0° | fire_intensity=0.00\n"
            "  NE: 1.0mi → fuel continues beyond trace limit | fuel=0.60 | moisture=0.70 | slope=0.0° | fire_intensity=0.00\n"
            "  E : 1.0mi → fuel continues beyond trace limit | fuel=0.59 | moisture=0.71 | slope=0.0° | fire_intensity=0.00 \U0001f525 WIND-ALIGNED\n"
            "  SE: 1.0mi → fuel continues beyond trace limit | fuel=0.61 | moisture=0.70 | slope=0.0° | fire_intensity=0.00\n"
            "  S : 1.0mi → fuel continues beyond trace limit | fuel=0.59 | moisture=0.69 | slope=0.0° | fire_intensity=0.00\n"
            "  SW: 1.0mi → fuel continues beyond trace limit | fuel=0.60 | moisture=0.70 | slope=0.0° | fire_intensity=0.00\n"
            "  W : 1.0mi → fuel continues beyond trace limit | fuel=0.58 | moisture=0.72 | slope=0.0° | fire_intensity=0.00\n"
            "  NW: 1.0mi → fuel continues beyond trace limit | fuel=0.61 | moisture=0.71 | slope=0.0° | fire_intensity=0.00"
        ),
        forecast=_forecast(13.0, 82.0, 2.0, "E", 0.70, precip_pct=30.0),
        history=_history(11.0, 88.0, 1.5, "E", 0.72, rain="0.02 inches  per hour "),
        expect_escalate=False,
        expect_confidence="high",
        notes="Sanity / false-positive guard. Suppress this and you can trust the False path.",
    ),

    EscalationCase(
        id="not_burnable",
        description="Hot and dry air over bare rock — atmospheric danger, zero fuel.",
        cell=_cell(
            10, 10,
            terrain_type=TerrainType.ROCK,
            vegetation=0.0,
            temperature_c=44.0,
            humidity_pct=9.0,
            wind_speed_mps=15.0,
            wind_direction_deg=180.0,
            fuel_moisture=0.05,
        ),
        scenario_text=(
            "Hotspot at (10, 10): Risk=0/10, Confidence=3/3\n"
            "Radial sector analysis:\n"
            "  N : 0.0mi → ROCK (natural firebreak) | fuel=0.00 | moisture=0.05 | slope=0.0° | fire_intensity=0.00\n"
            "  NE: 0.0mi → ROCK (natural firebreak) | fuel=0.00 | moisture=0.05 | slope=0.0° | fire_intensity=0.00\n"
            "  E : 0.0mi → ROCK (natural firebreak) | fuel=0.00 | moisture=0.05 | slope=0.0° | fire_intensity=0.00\n"
            "  SE: 0.0mi → ROCK (natural firebreak) | fuel=0.00 | moisture=0.05 | slope=0.0° | fire_intensity=0.00\n"
            "  S : 0.0mi → ROCK (natural firebreak) | fuel=0.00 | moisture=0.05 | slope=0.0° | fire_intensity=0.00 \U0001f525 WIND-ALIGNED\n"
            "  SW: 0.0mi → ROCK (natural firebreak) | fuel=0.00 | moisture=0.05 | slope=0.0° | fire_intensity=0.00\n"
            "  W : 0.0mi → ROCK (natural firebreak) | fuel=0.00 | moisture=0.05 | slope=0.0° | fire_intensity=0.00\n"
            "  NW: 0.0mi → ROCK (natural firebreak) | fuel=0.00 | moisture=0.05 | slope=0.0° | fire_intensity=0.00"
        ),
        forecast=_forecast(45.0, 8.0, 16.0, "N", 0.05),
        history=_history(41.0, 11.0, 14.0, "N", 0.06),
        expect_escalate=False,
        expect_confidence="high",
        notes="Burnability rule: scary weather over non-fuel is not a fire risk.",
    ),

    EscalationCase(
        id="borderline",
        description="Moderate conditions all-around — genuinely ambiguous.",
        cell=_cell(
            10, 10,
            temperature_c=33.0,
            humidity_pct=16.0,
            wind_speed_mps=10.0,
            wind_direction_deg=270.0,
            vegetation=0.5,
            fuel_moisture=0.25,
        ),
        scenario_text=(
            "Hotspot at (10, 10): Risk=5/10, Confidence=1/3\n"
            "Radial sector analysis:\n"
            "  N : 1.0mi → fuel continues beyond trace limit | fuel=0.49 | moisture=0.25 | slope=0.0° | fire_intensity=0.00\n"
            "  NE: 1.0mi → fuel continues beyond trace limit | fuel=0.51 | moisture=0.24 | slope=0.0° | fire_intensity=0.00\n"
            "  E : 1.0mi → fuel continues beyond trace limit | fuel=0.50 | moisture=0.25 | slope=0.0° | fire_intensity=0.00\n"
            "  SE: 1.0mi → fuel continues beyond trace limit | fuel=0.48 | moisture=0.26 | slope=0.0° | fire_intensity=0.00\n"
            "  S : 1.0mi → fuel continues beyond trace limit | fuel=0.50 | moisture=0.25 | slope=0.0° | fire_intensity=0.00\n"
            "  SW: 1.0mi → fuel continues beyond trace limit | fuel=0.51 | moisture=0.24 | slope=0.0° | fire_intensity=0.00\n"
            "  W : 1.0mi → fuel continues beyond trace limit | fuel=0.49 | moisture=0.25 | slope=0.0° | fire_intensity=0.00 \U0001f525 WIND-ALIGNED\n"
            "  NW: 1.0mi → fuel continues beyond trace limit | fuel=0.50 | moisture=0.25 | slope=0.0° | fire_intensity=0.00"
        ),
        forecast=_forecast(34.0, 15.0, 10.0, "W", 0.24),
        history=_history(31.0, 18.0, 9.0, "W", 0.27),
        expect_escalate=None,
        expect_confidence="low",
        notes="Calibration: model should not be confident here. Either call is defensible.",
    ),

    EscalationCase(
        id="mixed_signals",
        description="Hot, dry air over recently-soaked fuel — atmosphere says risk, fuel says no.",
        cell=_cell(
            10, 10,
            temperature_c=40.0,
            humidity_pct=12.0,
            wind_speed_mps=14.0,
            wind_direction_deg=315.0,
            vegetation=0.70,
            fuel_moisture=0.75,
        ),
        scenario_text=(
            "Hotspot at (10, 10): Risk=3/10, Confidence=2/3\n"
            "Radial sector analysis:\n"
            "  N : 1.0mi → fuel continues beyond trace limit | fuel=0.69 | moisture=0.74 | slope=0.0° | fire_intensity=0.00\n"
            "  NE: 1.0mi → fuel continues beyond trace limit | fuel=0.71 | moisture=0.75 | slope=0.0° | fire_intensity=0.00\n"
            "  E : 1.0mi → fuel continues beyond trace limit | fuel=0.68 | moisture=0.76 | slope=0.0° | fire_intensity=0.00\n"
            "  SE: 1.0mi → fuel continues beyond trace limit | fuel=0.70 | moisture=0.75 | slope=0.0° | fire_intensity=0.00\n"
            "  S : 1.0mi → fuel continues beyond trace limit | fuel=0.71 | moisture=0.74 | slope=0.0° | fire_intensity=0.00\n"
            "  SW: 1.0mi → fuel continues beyond trace limit | fuel=0.69 | moisture=0.75 | slope=0.0° | fire_intensity=0.00\n"
            "  W : 1.0mi → fuel continues beyond trace limit | fuel=0.70 | moisture=0.76 | slope=0.0° | fire_intensity=0.00\n"
            "  NW: 1.0mi → fuel continues beyond trace limit | fuel=0.71 | moisture=0.75 | slope=0.0° | fire_intensity=0.00 \U0001f525 WIND-ALIGNED"
        ),
        forecast=_forecast(41.0, 11.0, 14.0, "NW", 0.70),
        history=_history(37.0, 15.0, 12.0, "NW", 0.80, rain="0.03 inches  per hour "),
        expect_escalate=False,
        expect_confidence="low",
        expect_keywords=("moisture",),
        notes="Reconciliation: wet fuel should temper the decision AND moisture must appear in reasoning.",
    ),

    EscalationCase(
        id="shifting_wind",
        description="High-danger cell with conflicting surrounding wind directions — spread direction unknown.",
        cell=_cell(
            10, 10,
            temperature_c=38.0,
            humidity_pct=14.0,
            wind_speed_mps=16.0,
            wind_direction_deg=10.0,
            vegetation=0.70,
            fuel_moisture=0.15,
        ),
        scenario_text=(
            "Hotspot at (10, 10): Risk=8/10, Confidence=1/3\n"
            "Radial sector analysis:\n"
            "  N : 1.0mi → fuel continues beyond trace limit | fuel=0.69 | moisture=0.15 | slope=0.0° | fire_intensity=0.00 \U0001f525 WIND-ALIGNED\n"
            "  NE: 1.0mi → fuel continues beyond trace limit | fuel=0.71 | moisture=0.15 | slope=0.0° | fire_intensity=0.00\n"
            "  E : 1.0mi → fuel continues beyond trace limit | fuel=0.70 | moisture=0.16 | slope=0.0° | fire_intensity=0.00\n"
            "  SE: 1.0mi → fuel continues beyond trace limit | fuel=0.68 | moisture=0.16 | slope=0.0° | fire_intensity=0.00\n"
            "  S : 1.0mi → fuel continues beyond trace limit | fuel=0.70 | moisture=0.15 | slope=0.0° | fire_intensity=0.00\n"
            "  SW: 1.0mi → fuel continues beyond trace limit | fuel=0.71 | moisture=0.16 | slope=0.0° | fire_intensity=0.00\n"
            "  W : 1.0mi → fuel continues beyond trace limit | fuel=0.69 | moisture=0.15 | slope=0.0° | fire_intensity=0.00\n"
            "  NW: 1.0mi → fuel continues beyond trace limit | fuel=0.70 | moisture=0.16 | slope=0.0° | fire_intensity=0.00\n"
            "\n"
            "NOTE: Nearby cells (10,11) report wind_direction=110° and (11,10) report wind_direction=250°.\n"
            "Wind direction is inconsistent across this sector — spread direction is uncertain."
        ),
        forecast=_forecast(39.0, 13.0, 17.0, "variable", 0.14),
        history=_history(36.0, 16.0, 14.0, "variable", 0.17),
        expect_escalate=True,
        expect_confidence=None,
        notes=(
            "Dangerous fuel+weather → should escalate. Confidence behavior under "
            "directional ambiguity is what to watch."
        ),
    ),
]
