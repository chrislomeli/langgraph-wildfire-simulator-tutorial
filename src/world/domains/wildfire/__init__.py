"""
world-simulator.domains.wildfire

Wildfire domain — cell state, physics, fuel models, NWCG resources,
hardcoded-scenario factories.

The scripted plan-driven physics is the production path
(see [[scripted-trend-driver]]). Rothermel and Simple physics modules
are retained pending removal in task #6.

Sensors are not part of this package — see [[clean-data-no-sensor-noise]]
for the architectural decision and [[pod-architecture]] for how the
agent reads the world without sensors.
"""

from world.domains.wildfire.cell_state import FireCellState as FireCellState
from world.domains.wildfire.cell_state import FireState as FireState
from world.domains.wildfire.cell_state import TerrainType as TerrainType
from world.domains.wildfire.environment import FireEnvironmentState as FireEnvironmentState
from world.domains.wildfire.fuel_models import FuelModel as FuelModel
from world.domains.wildfire.fuel_models import get_fuel_model as get_fuel_model
from world.domains.wildfire.nwcg_resources import NWCGResourceSpec as NWCGResourceSpec
from world.domains.wildfire.nwcg_resources import get_by_id as get_by_id
from world.domains.wildfire.nwcg_resources import get_by_kind as get_by_kind
from world.domains.wildfire.nwcg_resources import suppression_category as suppression_category
from world.domains.wildfire.physics import FirePhysicsModule as FirePhysicsModule
from world.domains.wildfire.physics import SimpleFirePhysicsModule as SimpleFirePhysicsModule
from world.domains.wildfire.rothermel_physics import (
    RothermelFirePhysicsModule as RothermelFirePhysicsModule,
)
from world.domains.wildfire.scripted_trend_physics import (
    ScriptedTrendPhysics as ScriptedTrendPhysics,
)
from world.domains.wildfire.scenarios import create_basic_wildfire as create_basic_wildfire
from world.domains.wildfire.scenarios import (
    create_full_wildfire_scenario as create_full_wildfire_scenario,
)
from world.domains.wildfire.scenarios import create_wildfire_resources as create_wildfire_resources

__all__ = [
    # Cell state
    "FireCellState",
    "FireState",
    "TerrainType",
    # Environment
    "FireEnvironmentState",
    # Physics
    "FirePhysicsModule",
    "SimpleFirePhysicsModule",
    "RothermelFirePhysicsModule",
    "ScriptedTrendPhysics",
    # Fuel models
    "FuelModel",
    "get_fuel_model",
    # NWCG resources
    "NWCGResourceSpec",
    "get_by_id",
    "get_by_kind",
    "suppression_category",
    # Scenario factories (hardcoded; kept for tests)
    "create_basic_wildfire",
    "create_wildfire_resources",
    "create_full_wildfire_scenario",
]
