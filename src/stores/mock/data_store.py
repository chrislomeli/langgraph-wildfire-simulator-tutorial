"""Mock DataStore facade — assembles the JSON-backed repositories.

Drop-in replacement for PostgresDataStore when no database is available.

Usage::

    from stores.mock import get_mock_data_store
    from world.domains.wildfire.scenario_loader import start_world_service

    data_store = get_mock_data_store()
    engine = start_world_service(region_name="lpnf-south", data_store=data_store)
"""

from __future__ import annotations

from stores.base import (
    AdvisoryRepository,
    DataStore,
    ResourceRepository,
    ScenarioPlanRepository,
    TerrainRepository,
    WildfireRepository,
)
from stores.mock.advisory_repo import MockAdvisoryRepository
from stores.mock.resources_repo import MockResourceRepository
from stores.mock.scenario_plan_repo import MockScenarioPlanRepository
from stores.mock.terrain_repo import MockTerrainRepository
from stores.mock.wildfire_repo import MockWildfireRepository


class MockDataStore(DataStore):
    """DataStore backed by static JSON files — no Postgres or PostGIS required."""

    def __init__(self) -> None:
        self._terrain = MockTerrainRepository()
        self._wildfires = MockWildfireRepository()
        self._resources = MockResourceRepository()
        self._advisories = MockAdvisoryRepository()
        self._scenario_plan = MockScenarioPlanRepository()

    @property
    def terrain(self) -> TerrainRepository:
        return self._terrain

    @property
    def wildfires(self) -> WildfireRepository:
        return self._wildfires

    @property
    def resources(self) -> ResourceRepository:
        return self._resources

    @property
    def advisories(self) -> AdvisoryRepository:
        return self._advisories

    @property
    def scenario_plan(self) -> ScenarioPlanRepository:
        return self._scenario_plan


_instance: MockDataStore | None = None


def get_mock_data_store() -> MockDataStore:
    """Return the module-level MockDataStore singleton."""
    global _instance
    if _instance is None:
        _instance = MockDataStore()
    return _instance
