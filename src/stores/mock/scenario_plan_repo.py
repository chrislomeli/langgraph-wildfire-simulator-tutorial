"""Mock scenario plan repository — no scripted ramps.

An empty plan is fully valid: every cell stays static at its seed value.
Mock/stub mode does not script scenarios.
"""

from __future__ import annotations

from stores.base import ScenarioPlanRepository as ScenarioPlanRepositoryBase
from stores.schemas import ScenarioPlanSegment


class MockScenarioPlanRepository(ScenarioPlanRepositoryBase):
    """Returns an empty plan — all cells frozen at their seed values."""

    def fetch_plan(
        self, region_name: str
    ) -> dict[tuple[int, int, int], list[ScenarioPlanSegment]]:
        return {}
