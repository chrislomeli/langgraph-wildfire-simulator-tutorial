"""evals.logistics.cases — self-contained golden cases for the logistics eval.

Each LogisticsCase carries everything the LogisticsGraph needs:
  - situation_summary  : pre-authored supervisor context string
  - escalations        : pre-authored list of escalation+scenario dicts
  - tool_responses     : authored responses for get_resources_within and
                         get_wildfire_activity — returned by mock tools
                         regardless of the arguments the LLM passes in

Mock tools
──────────
build_mock_tools() returns LangChain-compatible tool callables whose names
and signatures match the real tools. The LLM experiences a complete tool
call/response cycle; only the implementation differs — it ignores the
arguments and returns the authored response. This keeps cases self-contained
while exercising the full ReAct loop in the trace.

Pydantic model so LangSmith can round-trip through seed_dataset /
make_target without a custom serializer. build_mock_tools() is excluded
from serialization (it's a method, not a field).
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class LogisticsCase(BaseModel):
    id: str
    description: str
    situation_summary: str
    escalations: list[dict]
    tool_responses: dict[str, Any] = Field(default_factory=dict)
    expect_advisory: bool | None = None
    advisory_criteria: str = ""
    notes: str = ""

    def build_mock_tools(self) -> list:
        """Return mock tool callables whose names match the real tools.

        The LLM calls these by name during the ReAct loop. Each mock ignores
        its arguments and returns the authored response from tool_responses.
        """
        resources_response = self.tool_responses.get(
            "get_resources_within", {"resources": [], "total": 0}
        )
        wildfire_response = self.tool_responses.get("get_wildfire_activity", [])

        @tool
        def get_resources_within(cell_row: int, cell_col: int, max_distance_mi: float) -> dict:
            """Get all firefighting resources within a radius of a grid cell.

            Returns available and committed resources sorted by distance. For
            committed resources, includes the fire they are currently assigned to
            so the LLM can weigh whether to request reassignment.

            Args:
                cell_row: Grid row of the ignition cell (0-indexed, north=0).
                cell_col: Grid column of the ignition cell (0-indexed, west=0).
                max_distance_mi: Search radius in miles.
            """
            return resources_response

        @tool
        def get_wildfire_activity(
            min_acres: float,
            max_acres: float,
            top: int,
        ) -> list:
            """Get historical wildfire incidents within an acreage range.

            Use this to benchmark how many crews, engines, and helicopters were
            historically deployed to fires of a similar size. Results are sorted
            most-recent first.
            """
            return wildfire_response

        return [get_resources_within, get_wildfire_activity]


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
        "radial_trace": {
            "epicenter_row": row,
            "epicenter_col": col,
            "sectors": sectors,
        },
    }


def _resource(
    resource_id: int,
    resource_type: str,
    station_name: str,
    distance_miles: float,
    status: str = "available",
    nwcg_type: str | None = None,
    personnel: int | None = None,
) -> dict:
    return {
        "resource_id": resource_id,
        "resource_type": resource_type,
        "station_name": station_name,
        "distance_miles": distance_miles,
        "status": status,
        "nwcg_type": nwcg_type,
        "personnel": personnel,
    }


# ── Cases ─────────────────────────────────────────────────────────────────────

def build_cases() -> list[LogisticsCase]:
    """Build and return the golden case list.

    Called by LogisticsDataset.load() — not at import time.
    """
    return [

    LogisticsCase(
        id="wind_aligned_urban_threat",
        description="Hotspot with long wind-aligned spread path into urban area, no resources within range.",
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
        tool_responses={
            "get_resources_within": {"resources": [], "total": 0},
            "get_wildfire_activity": [
                {
                    "fire_name": "Cedar Pass Fire",
                    "fire_size_acres": 4200,
                    "personnel": 312,
                    "crews": 14,
                    "engines": 22,
                    "helicopters": 4,
                    "percent_containment": 85,
                }
            ],
        },
        expect_advisory=True,
        advisory_criteria=(
            "The assessment must identify the NE wind-aligned sector as the primary threat vector: "
            "38 miles of unbroken burnable fuel leading to an urban barrier means a residential area "
            "is the terminus of the spread path. At 22 m/s wind and 6% fuel moisture, travel time "
            "to that settlement is short. The absence of any resources within 30 miles is a critical "
            "gap — historical fires of comparable spread potential required 14+ crews and 22+ engines. "
            "The advisory must cite urgency, name the threatened area, and recommend pre-positioning "
            "resources between the hotspot and the settlement. "
            "A failing response notes the danger without connecting it to the specific urban terminus "
            "or the resource gap."
        ),
        notes="Clear dispatch case. High danger + zero resources = unambiguous advisory.",
    ),

    LogisticsCase(
        id="all_directions_blocked",
        description="Hotspot surrounded by barriers, adequate local resources — no advisory warranted.",
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
        tool_responses={
            "get_resources_within": {
                "resources": [
                    _resource(41, "Engine", "Station 7 — Ridgecrest", 3.8, personnel=4, nwcg_type="Type 3"),
                    _resource(42, "Engine", "Station 12 — Inyokern", 6.1, personnel=3, nwcg_type="Type 6"),
                ],
                "total": 2,
            },
            "get_wildfire_activity": [],
        },
        expect_advisory=False,
        advisory_criteria=(
            "The assessment must argue that natural and urban barriers cap spread in every direction "
            "before any significant population or asset is threatened. The wind-aligned W sector "
            "reaching a river at 4.8 miles is the key override. Two available engines within 6 miles "
            "provide adequate coverage for a hotspot with ignition_risk=4 and no unobstructed spread path. "
            "A failing response issues an advisory based on atmospheric conditions without weighing "
            "the barrier geometry, or ignores the available resources that make pre-positioning unnecessary."
        ),
        notes="False-positive guard. Barriers + adequate local resources = no advisory.",
    ),

    LogisticsCase(
        id="two_hotspots_converging",
        description="Two hotspots sharing a wind-aligned corridor toward the same urban area, no resources.",
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
        tool_responses={
            "get_resources_within": {"resources": [], "total": 0},
            "get_wildfire_activity": [
                {
                    "fire_name": "Juniper Mesa Fire",
                    "fire_size_acres": 8500,
                    "personnel": 587,
                    "crews": 26,
                    "engines": 38,
                    "helicopters": 6,
                    "percent_containment": 62,
                }
            ],
        },
        expect_advisory=True,
        advisory_criteria=(
            "The assessment must recognize that both hotspots share the same wind-aligned spread "
            "corridor targeting the same urban settlement — this is a compound threat, not two "
            "independent events. Zero resources within range of either hotspot means the entire "
            "corridor is unprotected. The advisory must cite the combined front width, the shared "
            "urban terminus, and the compounding resource gap. Historical fires of comparable size "
            "required 26+ crews — the absence of any local resources is a critical gap. "
            "A failing response treats the two hotspots as independent or issues only one advisory "
            "without acknowledging the compounding geometry."
        ),
        notes="Multi-hotspot coordination case. Compound threat + zero resources = advisory.",
    ),

    LogisticsCase(
        id="moderate_ambiguous",
        description="Moderate conditions, partial barriers, one borderline resource nearby — genuinely uncertain.",
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
        tool_responses={
            "get_resources_within": {
                "resources": [
                    _resource(88, "Engine", "Station 3 — Panamint Valley", 22.1, personnel=3, nwcg_type="Type 6"),
                ],
                "total": 1,
            },
            "get_wildfire_activity": [],
        },
        expect_advisory=None,
        advisory_criteria=(
            "The assessment must arrive at genuine uncertainty — not a confident decision dressed up "
            "as uncertainty. Moderate atmospheric conditions (32°C / 20% RH / ignition_risk=5), a "
            "partial urban barrier whose population density is unknown, stable fuel moisture, and one "
            "borderline resource 22 miles out create a real balance where no factor is decisive. "
            "One Type 6 engine at 22 miles is borderline adequate for a risk=5 hotspot — enough to "
            "argue either way. The rationale must name the specific unknowns that would resolve the "
            "ambiguity: population density behind the partial barrier, whether the single engine can "
            "reach in time given wind speed, or a deteriorating moisture trend. "
            "A failing response manufactures a confident advisory decision from these genuinely "
            "moderate inputs, or hedges without identifying the specific unknowns."
        ),
        notes="Calibration case. Moderate danger + borderline resource = genuinely ambiguous.",
    ),

    ]
