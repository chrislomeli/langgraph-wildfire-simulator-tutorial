"""Read-only view of the world for agent code.

The agent pipeline depends on ``WorldView`` rather than on the concrete
``GenericWorldEngine`` so that:

1. Agent code makes its world-state dependencies explicit at the type signature.
2. The boundary "what the agent can see" lives in one place.
3. The engine implementation can change without touching agents.

Convention: callers MUST treat the returned cells as read-only. Mutation
desyncs the in-memory grid from ``state_snapshot_log`` and from any future
persistence layer. The Protocol does not enforce this — discipline is by
convention, matching ``RiskView``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from world.cell_state import C, GenericCell


@runtime_checkable
class WorldView(Protocol[C]):
    """Read-only world surface used by agent nodes."""

    @property
    def rows(self) -> int: ...

    @property
    def cols(self) -> int: ...

    @property
    def cell_size_ft(self) -> float: ...

    def get_cell(self, row: int, col: int, layer: int = 0) -> GenericCell[C]: ...
