"""evals.logistics.cases — self-contained golden cases for the logistics eval.

Each LogisticsCase carries everything the LogisticsGraph needs:
  - situation_summary : pre-authored supervisor context string
  - escalations       : pre-authored list of escalation+scenario dicts

No world engine, DB, or tool results are required — cases are authored
directly so we control the spread geometry and can craft scenarios that
test specific advisory reasoning (converging paths, barrier containment,
compound threats).

Pydantic model so LangSmith can round-trip through seed_dataset /
make_target without a custom serializer.
"""

from __future__ import annotations

from pydantic import BaseModel


class LogisticsCase(BaseModel):
    id: str
    description: str
    situation_summary: str
    escalations: list[dict]
    expect_advisory: bool | None = None
    advisory_criteria: str = ""
    notes: str = ""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sector(
    direction: str,
    burnable_miles: float,
    stop_reason: str,
    avg_vegetation: float,
    avg_fuel_moisture: float,
    *,
    wind_aligned: bool = False,
    cells_in_sector: int = 10,
) -> dict:
    return {
        "direction": direction,
        "burnable_miles": burnable_miles,
        "stop_reason": stop_reason,
        "avg_vegetation": avg_vegetation,
        "avg_fuel_moisture": avg_fuel_moisture,
        "avg_slope": 0.0,
        "max_fire_intensity": 0.0,
        "wind_aligned": wind_aligned,
        "cells_in_sector": cells_in_sector,
    }


def _escalation(
    row: int,
    col: int,
    *,
    factors: dict,
    reasoning: str,
    sectors: list[dict],
) -> dict:
    return {
        "escalation": {
            "factors": factors,
            "reasoning": reasoning,
            "escalate": True,
            "sector_id": f"sector({row},{col})",
            "row": row,
            "col": col,
            "layer": 0,
        },
        "scenario": {
            "epicenter_row": row,
            "epicenter_col": col,
            "sectors": sectors,
        },
    }


# ── Cases ─────────────────────────────────────────────────────────────────────

def build_cases() -> list[LogisticsCase]:
    """Build and return the golden case list.

    Called by LogisticsDataset.load() — not at import time.
    """
    return [

    LogisticsCase(
        id="wind_aligned_urban_threat",
        description="Hotspot with long wind-aligned spread path into urban area — clear resource need.",
        situation_summary=(
            "Active wind event from SW. Temperature 41°C, humidity 9%. "
            "One hotspot escalated at (10,10). Spread path extends 38 miles NE toward residential settlement."
        ),
        escalations=[_escalation(
            10, 10,
            factors={
                "temperature_humidity": "Temperature 41°C with 9% relative humidity — critically dangerous combination.",
                "wind": "22 m/s SW wind aligned NE toward urban settlement over unbroken fuel corridor.",
                "fuel_and_terrain": "Dense cured grass, vegetation 0.82, flat terrain with no natural breaks.",
                "moisture_trend": "Fuel moisture 0.06 — 3-day drying trend from 0.12, no precipitation forecast.",
            },
            reasoning=(
                "All four axes compound. Wind-aligned NE spread path reaches urban settlement "
                "with no intervening barriers. Immediate resource deployment warranted."
            ),
            sectors=[
                _sector("N",   6.0,  "grid_edge",     0.30, 0.09),
                _sector("NE", 38.4,  "barrier:urban", 0.78, 0.06, wind_aligned=True, cells_in_sector=32),
                _sector("E",  12.0,  "barrier:urban", 0.45, 0.07),
                _sector("SE",  6.0,  "grid_edge",     0.20, 0.08),
                _sector("S",   6.0,  "grid_edge",     0.25, 0.09),
                _sector("SW",  6.0,  "grid_edge",     0.30, 0.08),
                _sector("W",   6.0,  "grid_edge",     0.28, 0.07),
                _sector("NW",  8.4,  "barrier:urban", 0.35, 0.07),
            ],
        )],
        expect_advisory=True,
        advisory_criteria=(
            "The assessment must identify the NE wind-aligned sector as the primary threat vector: "
            "38 miles of unbroken burnable fuel leading to an urban barrier means a residential area "
            "is the terminus of the spread path. At 22 m/s wind and 6% fuel moisture, travel time "
            "to that settlement is short. The advisory must cite urgency, name the threatened area, "
            "and recommend pre-positioning resources between the hotspot and the settlement. "
            "A failing response notes the danger without connecting it to the specific urban terminus "
            "or withholds an advisory because no tool-sourced resource data was available."
        ),
        notes="Clear dispatch case. Tests whether the agent acts on spread-path geometry from input data alone.",
    ),

    LogisticsCase(
        id="all_directions_blocked",
        description="Hotspot surrounded by barriers — spread is physically contained, no advisory warranted.",
        situation_summary=(
            "Isolated hotspot at (20,20). Temperature 34°C, humidity 18%. "
            "All radial sectors blocked within 10 miles by urban, water, or rock barriers."
        ),
        escalations=[_escalation(
            20, 20,
            factors={
                "temperature_humidity": "Temperature 34°C, humidity 18% — elevated but not at critical threshold.",
                "wind": "12 m/s NW wind. Wind-aligned W sector blocked at 4.8 miles by river.",
                "fuel_and_terrain": "Moderate vegetation 0.45. Rock barriers to N and E limit spread.",
                "moisture_trend": "Fuel moisture 0.22 — slightly elevated, stable trend, no drying.",
            },
            reasoning=(
                "Escalated due to atmospheric conditions, but all spread sectors blocked within "
                "10 miles. No open corridor reaches a population or asset."
            ),
            sectors=[
                _sector("N",   4.8, "barrier:rock",  0.20, 0.22),
                _sector("NE",  6.0, "grid_edge",     0.30, 0.20),
                _sector("E",   3.6, "barrier:rock",  0.15, 0.23),
                _sector("SE",  7.2, "barrier:urban", 0.35, 0.21),
                _sector("S",   9.6, "barrier:urban", 0.40, 0.20),
                _sector("SW",  6.0, "barrier:water", 0.25, 0.22),
                _sector("W",   4.8, "barrier:water", 0.22, 0.23, wind_aligned=True),
                _sector("NW",  6.0, "grid_edge",     0.28, 0.21),
            ],
        )],
        expect_advisory=False,
        advisory_criteria=(
            "The assessment must argue that natural and urban barriers cap spread in every direction "
            "before any significant population or asset is threatened. The wind-aligned W sector "
            "reaching a river at 4.8 miles is the key override — even the primary spread vector is "
            "stopped by a natural firebreak. Moderate fuel moisture reinforces containment. "
            "A failing response issues an advisory based on atmospheric conditions without weighing "
            "the barrier geometry that physically prevents any spread scenario from materializing."
        ),
        notes="False-positive guard. Barriers should suppress the advisory even with moderate atmospheric risk.",
    ),

    LogisticsCase(
        id="two_hotspots_converging",
        description="Two hotspots with overlapping eastward spread paths toward a shared urban corridor.",
        situation_summary=(
            "Two hotspots escalated: (5,5) and (15,5). Both show eastward wind-aligned spread paths "
            "extending 30+ miles toward the same urban corridor. Temperature 39°C, humidity 11%, "
            "sustained 18 m/s eastward wind."
        ),
        escalations=[
            _escalation(
                5, 5,
                factors={
                    "temperature_humidity": "39°C, 11% humidity — critically dry and hot.",
                    "wind": "18 m/s E wind. Wind-aligned E sector extends 33.6 miles to urban barrier.",
                    "fuel_and_terrain": "Dense grass, vegetation 0.75, no natural breaks eastward.",
                    "moisture_trend": "Fuel moisture 0.07, 4-day drying trend, no precipitation forecast.",
                },
                reasoning=(
                    "High ignition risk with unobstructed wind-aligned path into urban corridor. "
                    "Compounded by second hotspot sharing the same corridor at (15,5)."
                ),
                sectors=[
                    _sector("N",   6.0,  "grid_edge",     0.25, 0.10),
                    _sector("NE", 12.0,  "barrier:urban", 0.40, 0.08),
                    _sector("E",  33.6,  "barrier:urban", 0.75, 0.07, wind_aligned=True, cells_in_sector=28),
                    _sector("SE", 20.4,  "barrier:urban", 0.55, 0.08),
                    _sector("S",   9.6,  "barrier:urban", 0.35, 0.09),
                    _sector("SW",  6.0,  "grid_edge",     0.20, 0.10),
                    _sector("W",   6.0,  "grid_edge",     0.22, 0.10),
                    _sector("NW",  6.0,  "grid_edge",     0.28, 0.09),
                ],
            ),
            _escalation(
                15, 5,
                factors={
                    "temperature_humidity": "39°C, 11% humidity — same atmospheric system as northern hotspot.",
                    "wind": "18 m/s E wind. Wind-aligned E sector extends 28.8 miles to the same urban barrier.",
                    "fuel_and_terrain": "Similar dense grass corridor, no barriers between hotspot and settlement.",
                    "moisture_trend": "Fuel moisture 0.08, consistent with northern hotspot drying trend.",
                },
                reasoning=(
                    "Second hotspot on the same eastward wind-aligned corridor as (5,5). "
                    "Combined threat to the urban corridor is greater than either hotspot alone."
                ),
                sectors=[
                    _sector("N",   6.0,  "grid_edge",     0.22, 0.10),
                    _sector("NE", 14.4,  "barrier:urban", 0.45, 0.09),
                    _sector("E",  28.8,  "barrier:urban", 0.70, 0.08, wind_aligned=True, cells_in_sector=24),
                    _sector("SE", 16.8,  "barrier:urban", 0.50, 0.09),
                    _sector("S",   7.2,  "barrier:urban", 0.30, 0.10),
                    _sector("SW",  6.0,  "grid_edge",     0.18, 0.11),
                    _sector("W",   6.0,  "grid_edge",     0.20, 0.10),
                    _sector("NW",  6.0,  "grid_edge",     0.25, 0.10),
                ],
            ),
        ],
        expect_advisory=True,
        advisory_criteria=(
            "The assessment must recognize that both hotspots share the same wind-aligned spread "
            "corridor targeting the same urban settlement — this is a compound threat, not two "
            "independent events. The advisory must cite the combined front width (two origins feeding "
            "the same corridor), the shared urban terminus, and the implication for resource positioning "
            "(covering both flanks, not just one origin point). "
            "A failing response treats the two hotspots as independent and recommends separate "
            "uncoordinated responses, or issues only one advisory without acknowledging the "
            "compounding geometry."
        ),
        notes="Multi-hotspot coordination case. Tests whether the agent synthesizes a compound threat.",
    ),

    LogisticsCase(
        id="moderate_ambiguous",
        description="Single hotspot, moderate conditions, partial barriers — genuinely uncertain.",
        situation_summary=(
            "One hotspot at (12,18). Temperature 32°C, humidity 20%. Moderate 9 m/s wind. "
            "Partial barriers in wind-aligned direction at 15 miles. No confirmed settlement within spread path."
        ),
        escalations=[_escalation(
            12, 18,
            factors={
                "temperature_humidity": "32°C, 20% humidity — elevated but not at critical threshold.",
                "wind": "9 m/s SW wind. Wind-aligned NE sector reaches partial urban barrier at 15.6 miles.",
                "fuel_and_terrain": "Moderate vegetation 0.50. Mixed terrain, some open areas.",
                "moisture_trend": "Fuel moisture 0.20 — stable, no strong drying or wetting trend.",
            },
            reasoning=(
                "Conditions elevated but no single factor at critical threshold. Wind-aligned path "
                "reaches a partial barrier that may or may not contain spread."
            ),
            sectors=[
                _sector("N",  14.4, "barrier:urban", 0.45, 0.20),
                _sector("NE", 15.6, "barrier:urban", 0.50, 0.19, wind_aligned=True, cells_in_sector=13),
                _sector("E",  19.2, "max_distance",  0.42, 0.21),
                _sector("SE", 10.8, "barrier:urban", 0.38, 0.22),
                _sector("S",   8.4, "barrier:urban", 0.35, 0.21),
                _sector("SW",  6.0, "grid_edge",     0.28, 0.22),
                _sector("W",   6.0, "grid_edge",     0.30, 0.20),
                _sector("NW",  9.6, "barrier:rock",  0.25, 0.23),
            ],
        )],
        expect_advisory=None,
        advisory_criteria=(
            "The assessment must arrive at genuine uncertainty — not a confident decision dressed up "
            "as uncertainty. Moderate atmospheric conditions (32°C / 20% RH), a partial urban barrier "
            "whose population density is unknown, and stable fuel moisture create a real balance where "
            "no factor is decisive. The rationale must name what would resolve the ambiguity: confirmed "
            "population density behind the barrier, resource pre-positioning cost, or a fuel moisture "
            "trend. A failing response manufactures a confident advisory decision from genuinely moderate "
            "inputs, or hedges without identifying the specific unknowns that make the case borderline."
        ),
        notes="Calibration case. Model should acknowledge uncertainty and name what would resolve it.",
    ),

    ]
