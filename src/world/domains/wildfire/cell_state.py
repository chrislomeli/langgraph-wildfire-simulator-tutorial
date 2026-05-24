"""
world-simiulator.domains.wildfire.cell_state

FireCellState — per-cell state for wildfire simulation.

This defines what data lives on each grid cell in a wildfire scenario:
  - terrain_type : what kind of land (forest, grassland, rock, etc.)
  - vegetation   : density of burnable material (0.0–1.0)
  - fuel_moisture: how wet the fuel is (0.0–1.0)
  - slope        : gradient in degrees
  - fire_state   : UNBURNED, BURNING, or BURNED
  - fire_intensity: how hot the fire is (0.0–1.0)
  - fire_start_tick: when the fire started in this cell

TerrainType and FireState enums are imported from world-simiulator.world.grid
(their original home) and re-exported here so that domain code can
import everything from one place.
"""

from __future__ import annotations

from world.cell_state import CellState
from world.grid import FireState, TerrainCode, TerrainType

# ── Cell state ───────────────────────────────────────────────────────────────


class FireCellState(CellState):
    """
    {
      "source": "RMRS-GTR-153",
      "artifact_type": "cell_state_field_mappings",
      "description": "Explicit mapping between cell_state database columns and fire behavior fuel model concepts. Use this to translate sensor readings into fuel model reasoning inputs.",
      "mappings": {
        "fuel_type_number_blocks": {
          "description": "Fuel model number ranges assigned per fuel type for mapping applications.",
          "NB": {
            "range": "90-99",
            "label": "Nonburnable"
          },
          "GR": {
            "range": "100-119",
            "label": "Grass"
          },
          "GS": {
            "range": "120-139",
            "label": "Grass-Shrub"
          },
          "SH": {
            "range": "140-159",
            "label": "Shrub"
          },
          "TU": {
            "range": "160-179",
            "label": "Timber-Understory"
          },
          "TL": {
            "range": "180-199",
            "label": "Timber Litter"
          },
          "SB": {
            "range": "200-219",
            "label": "Slash-Blowdown"
          }
        },
        "fuel_moisture": {
          "document_concept": "Dead fuel moisture content",
          "reasoning_guidance": "Map to dead fuel moisture scenarios D1-D4. Values below 6% approach D1 (Very Low). Values 6-9% map to D2 (Low). Values 9-12% map to D3 (Moderate). Values above 12% map to D4 (High). For dynamic fuel models, also estimate live herbaceous moisture using the herbaceous_curing_table if curing level is observable.",
          "scenario_thresholds": {
            "D1_Very_Low": {
              "1hr_pct_max": 3
            },
            "D2_Low": {
              "1hr_pct_max": 6
            },
            "D3_Moderate": {
              "1hr_pct_max": 9
            },
            "D4_High": {
              "1hr_pct_max": 12
            }
          }
        },
        "vegetation": {
          "document_concept": "Live herbaceous moisture content / degree of curing",
          "reasoning_guidance": "NDVI is a proxy for vegetation greenness and live fuel moisture. High NDVI (approaching 1.0) suggests uncured, green vegetation with live herbaceous moisture >= 120%. Low NDVI (approaching 0) suggests cured or absent vegetation with live herbaceous moisture <= 30%. Use as a continuous signal to interpolate live moisture scenario L1-L4 and to determine whether dynamic fuel models will transfer herbaceous load to dead.",
          "ndvi_interpretation": {
            "high_green": {
              "ndvi_approx": ">0.5",
              "live_herb_moisture": ">=120%",
              "curing": "Uncured",
              "live_scenario": "L4"
            },
            "moderate_green": {
              "ndvi_approx": "0.3 to 0.5",
              "live_herb_moisture": "75-120%",
              "curing": "Partly Cured",
              "live_scenario": "L3"
            },
            "low_green": {
              "ndvi_approx": "0.1 to 0.3",
              "live_herb_moisture": "30-75%",
              "curing": "Mostly Cured",
              "live_scenario": "L2"
            },
            "cured": {
              "ndvi_approx": "<0.1",
              "live_herb_moisture": "<=30%",
              "curing": "Fully Cured",
              "live_scenario": "L1"
            }
          }
        },
        "temperature_c": {
          "document_concept": "Indirect influence on fuel moisture drying rate",
          "reasoning_guidance": "Not a direct fuel model input. High temperatures accelerate fuel drying, pushing dead fuel moisture toward lower scenarios (D1/D2). Use as a contextual signal when fuel_moisture reading is absent or uncertain."
        },
        "humidity_pct": {
          "document_concept": "Indirect influence on dead fuel moisture equilibrium",
          "reasoning_guidance": "Not a direct fuel model input. Low relative humidity (< 20%) is associated with D1/D2 dead fuel moisture scenarios and elevated fire risk. High humidity (> 60%) is associated with D3/D4 scenarios and suppressed spread."
        },
        "wind_speed_mps": {
          "document_concept": "Midflame wind speed",
          "reasoning_guidance": "Direct fire behavior driver. Fire behavior charts in the document use midflame wind speed in mi/h. Convert: 1 m/s = 2.237 mi/h. Standard comparison charts run from 0 to 20 mi/h. Wind speed is the primary driver of rate of spread increase across all fuel types.",
          "conversion": "mph = mps * 2.237"
        },
        "wind_direction_deg": {
          "document_concept": "Fire spread direction",
          "reasoning_guidance": "Used to determine headfire direction relative to fuel layout. Not a fuel model parameter per se, but critical for operational fire spread prediction. Combined with slope aspect, determines upslope/wind alignment scenarios.",
          "wind_direction_interpretation": "Wind direction is meteorological (wind comes from the stated bearing, clockwise from North). Fire spreads opposite: bearing + 180° mod 360°. Western longitudes are negative — \"more west\" means more negative. Example: 90° reading at POINT(-118.541837, 34.286735) → wind from East → fire spreads West → toward lower (more negative) longitudes "
        },
        "risk_score": {
          "document_concept": "Composite fire behavior risk assessment output",
          "reasoning_guidance": "Derived field — should reflect combination of fuel type, dead fuel moisture scenario, live moisture scenario, and wind speed. Use fuel model parameters and adjective class thresholds to validate or compute."
        }
      }
    }
    """

    # Terrain properties (set once during scenario setup, don't change)
    terrain_type: TerrainType = TerrainType.GRASSLAND
    terrain_code: TerrainCode = TerrainCode.GR
    slope: float = 0.0

    # Per-cell weather (seeded from DB, evolved by physics each tick)
    vegetation: float = 0.5
    fuel_moisture: float = 0.3
    temperature_c: float = 30.0
    humidity_pct: float = 25.0
    wind_speed_mps: float = 5.0
    wind_direction_deg: float = 0.0
    precipitation: float = 0.0
    pressure_hpa: float = 1013.0

    # Fire state (changes during simulation via StateEvents)
    fire_state: FireState = FireState.UNBURNED
    fire_intensity: float = 0.0
    fire_start_tick: int | None = None

    # Rothermel fire behavior metrics (populated by RothermelFirePhysicsModule)
    # Zero on unburned/burned cells; updated each tick on burning cells.
    rate_of_spread_ft_min: float = 0.0
    flame_length_ft: float = 0.0
    fireline_intensity_btu_ft_s: float = 0.0

    def to_local_conditions(self) -> dict[str, float | str]:
        """Return the per-cell ground truth as a local_conditions dict.

        This is what the sampler passes to sensor.emit(). Sensors pick
        out the keys they care about and add noise.
        """
        return {
            "ambient_temperature_c": self.temperature_c,
            "humidity_pct": self.humidity_pct,
            "wind_speed_mps": self.wind_speed_mps,
            "wind_direction_deg": self.wind_direction_deg,
            "pressure_hpa": self.pressure_hpa,
            "fuel_moisture": self.fuel_moisture,
            "vegetation": self.vegetation,
            "terrain_type": self.terrain_type.value,
            "fire_state": self.fire_state.value,
            "fire_intensity": self.fire_intensity,
            "precipitation" : self.precipitation,
        }

    def summary_label(self) -> str:
        """Used by the engine for logging and grid summary counts."""
        return self.fire_state.value

    @property
    def is_burnable(self) -> bool:
        """
        Can fire spread to this cell?

        Rock, water, and already-burned cells cannot catch fire.
        Cells with zero vegetation also cannot burn.
        """
        if self.terrain_type in (TerrainType.ROCK, TerrainType.WATER):
            return False
        if self.fire_state != FireState.UNBURNED:
            return False
        if self.vegetation <= 0.0:
            return False
        return True

    def ignited(
        self,
        tick: int,
        intensity: float = 0.5,
        rate_of_spread_ft_min: float = 0.0,
        flame_length_ft: float = 0.0,
        fireline_intensity_btu_ft_s: float = 0.0,
    ) -> FireCellState:
        """
        Return a new state with the cell on fire.

        Does NOT mutate self — returns a new instance for use in
        StateEvent. This is the immutable pattern the generic engine
        expects.

        Parameters
        ──────────
        tick                      : simulation tick at ignition
        intensity                 : normalized fire intensity 0.0–1.0
        rate_of_spread_ft_min     : Rothermel ROS at ignition (ft/min)
        flame_length_ft           : Byram flame length at ignition (ft)
        fireline_intensity_btu_ft_s: Byram fireline intensity (BTU/ft/s)
        """
        return self.model_copy(
            update={
                "fire_state": FireState.BURNING,
                "fire_intensity": max(0.0, min(1.0, intensity)),
                "fire_start_tick": tick,
                "rate_of_spread_ft_min": rate_of_spread_ft_min,
                "flame_length_ft": flame_length_ft,
                "fireline_intensity_btu_ft_s": fireline_intensity_btu_ft_s,
            }
        )

    def extinguished(self) -> FireCellState:
        """Return a new state with the fire burned out. Zeros out fire behavior metrics."""
        return self.model_copy(
            update={
                "fire_state": FireState.BURNED,
                "fire_intensity": 0.0,
                "rate_of_spread_ft_min": 0.0,
                "flame_length_ft": 0.0,
                "fireline_intensity_btu_ft_s": 0.0,
            }
        )
