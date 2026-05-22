"""Pydantic models for database tables."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class Resource(BaseModel):
    """Model for the resources table."""

    model_config = ConfigDict(populate_by_name=True)

    resource_id: int | None = None
    source_file: str | None = None
    agency: str | None = None
    cal_file_unit: str | None = None
    unit_id: str | None = None
    resource_category: str | None = None
    resource_type: str | None = None
    nwcg_type: str | None = None
    year: str | None = None
    male: str | None = None
    model: str | None = None
    capacity_water_gal: int | None = None
    pump_gpm: int | None = None
    personnel: int | None = None
    battalion: str | None = None
    station_number: str | None = None
    station_name: str | None = None
    station_address: str | None = None
    mutual_aid_agreement: str | None = None
    lpf_interface_priority: str | None = None
    seasonal: str | None = None
    lat: float | None = None
    long: float | None = None
    notes: str | None = None
    location: str | None = None  # geography(Point, 4326) as WKT string
    distance_miles: float | None = None  # Computed field — excluded from DB operations

    def to_db_row(self) -> tuple:
        """Return tuple for INSERT/UPDATE — computed fields excluded."""
        return (
            self.resource_id,
            self.source_file,
            self.agency,
            self.cal_file_unit,
            self.unit_id,
            self.resource_category,
            self.resource_type,
            self.nwcg_type,
            self.year,
            self.male,
            self.model,
            self.capacity_water_gal,
            self.pump_gpm,
            self.personnel,
            self.battalion,
            self.station_number,
            self.station_name,
            self.station_address,
            self.mutual_aid_agreement,
            self.lpf_interface_priority,
            self.seasonal,
            self.lat,
            self.long,
            self.notes,
            self.location,
        )


class Sensor(BaseModel):
    """Model for the sensors table."""

    model_config = ConfigDict(populate_by_name=True)

    grid_row: int | None = None
    grid_column: int | None = None
    elevation: int | None = None
    sensor_id: str  # PK, required
    sensor_type: str | None = None
    cluster_id: str | None = None
    noise_std: float | None = None
    lat: float | None = None
    long: float | None = None
    location: str | None = None  # geography(Point, 4326) as WKT string
    region: str | None = None


class TerrainState(BaseModel):
    """Model for the terrain table."""
    model_config = ConfigDict(populate_by_name=True)

    grid_column: int | None = None
    grid_row: int | None = None
    layer: int | None = None
    region: str | None = None
    version: str | None = None
    # Per-cell weather seed (initial conditions at tick 0)
    fuel_moisture: float | None = None
    temperature_c: float | None = None
    humidity_pct: float | None = None
    wind_speed_mps: float | None = None
    wind_direction_deg: float | None = None
    pressure_hpa: float | None = None
    vegetation: float | None = None


class Terrain(TerrainState):
    """Model for the terrain table."""
    model_config = ConfigDict(populate_by_name=True)

    cell_key: str | None = None
    terrain: str | None = None
    terrain_type: str | None = None
    slope: float | None = None
    cell_size_ft: int | None = None
    time_step_min: float | None = None
    burn_duration_ticks: int | None = None
    lat: float | None = None
    long: float | None = None
    location: str | None = None  # geography(Point, 4326) as WKT string



class WildfireActivity(BaseModel):
    """Model for the wildfire_activity table."""
    model_config = ConfigDict(populate_by_name=True)

    imsr_date: date | None = None
    gacc: str | None = None
    gacc_priority: int | None = None
    fire_priority: int | None = None
    new_large_fire_mark: str  # NOT NULL
    fire_name: str | None = None
    unit: str | None = None
    fire_size_acres: int | None = None
    fire_size_change: str | None = None
    percent_containment: int | None = None
    contained_completed: str | None = None
    est_containment_date: str | None = None
    personnel: int | None = None
    personnel_change: str | None = None
    crews: int | None = None
    engines: int | None = None
    helicopters: int | None = None
    structures_lost: int | None = None
    cost_to_date: str | None = None
    origin_ownership: int | None = None


class ScenarioPlanSegment(BaseModel):
    """Model for one scenario_cell_plan row — a single scripted ramp segment."""

    model_config = ConfigDict(populate_by_name=True)

    region: str | None = None
    grid_row: int | None = None
    grid_column: int | None = None
    layer: int = 0
    metric: str
    start_tick: int = 0
    duration_ticks: int
    start_value: float | None = None  # NULL => resolve from the cell's value at start_tick
    target_value: float
    curve: str = "linear"
    hold_after: bool = True


# ResourceAdvisory is the agent's published output contract; the agent layer
# produces it and the stores layer persists it. It lives here (rather than in
# agents/) so stores can depend on it without inverting the layer dependency.
class ResourceAdvisory(BaseModel):
    """Structured advisory report for resource deployment decisions."""

    epicenter_row: int = Field(
        description="Terrain grid row index of the fire risk epicenter (highest-risk cell)."
    )

    epicenter_column: int = Field(
        description="Terrain grid column index of the fire risk epicenter (highest-risk cell)."
    )

    location_description: str = Field(
        description="Human-readable description of the affected area, especially for impact zones difficult to describe in grid coordinates (e.g., 'northwest slope below ridgeline')."
    )
    situation: str = Field(
        description="Current fire status, spread direction, and immediate threat level. 1-2 sentences."
    )

    urgency_level: int = Field(
        ge=1,
        le=4,
        description="""How urgent and immediate is this situation?

LEVEL 4 (Fade Out): Lowest readiness; routine monitoring.
LEVEL 3 (Double Take): Elevated readiness; increased monitoring.
LEVEL 2 (Fast Pace): High readiness; prepare for deployment.
LEVEL 1 (Cocked Pistol): Maximum readiness; imminent response required.
""",
    )
    notes: str = Field(
        description=(
            "Context, uncertainties, and edge-case reasoning. "
            "Discuss resource conflicts, conditional scenarios, or cascading risks. "
            "Example: '3 engines committed to 30%-contained Lompoc fire. "
            "If 2+ hotspots ignite simultaneously, Level 1 capacity exceeded.'"
        )
    )
    recommendation: str = Field(
        description="Specific action to take, or 'Monitor only' if no deployment needed."
    )


# Database view of the ResourceAdvisory adds tracking fields
class ResourceAdvisoryRecord(ResourceAdvisory):
    id: UUID = Field(default_factory=uuid4, description="Unique identifier. Generated on creation.")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: Literal["SENT", "SUPPRESSED", "ACKNOWLEDGED"] = Field(default="SENT")

    def to_db_row(self) -> tuple:
        """Return tuple for INSERT/UPDATE — computed fields excluded."""
        return (
            self.id,
            self.created_at,
            self.status,
            self.epicenter_row,
            self.epicenter_column,
            self.location_description,
            self.situation,
            self.urgency_level,
            self.notes,
            self.recommendation,
        )
