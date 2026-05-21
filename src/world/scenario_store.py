"""Narrow data-layer contract for the world-service.

What this is
────────────
The world-service reads exactly two things from its data layer: terrain
(static cell metadata + seed state) and a scenario plan (deterministic
weather trajectory). Everything else exposed by ``DataStore`` (sensors,
wildfires, resources, advisories) is advisory-side concern.

``ScenarioStore`` is the read surface world-service depends on. The
concrete ``DataStore`` implementations (``PostgresDataStore``,
``MockDataStore``) satisfy it structurally — no inheritance required.

When the world-service splits into its own pod (see [[pod-architecture]]),
the pod's DB client only needs to implement ``ScenarioStore``, not the
fat ``DataStore`` facade.
"""

from __future__ import annotations

from typing import Protocol

from stores.base import ScenarioPlanRepository, TerrainRepository


class ScenarioStore(Protocol):
    """The two repos the world-service needs to stand up a scenario."""

    @property
    def terrain(self) -> TerrainRepository: ...

    @property
    def scenario_plan(self) -> ScenarioPlanRepository: ...
