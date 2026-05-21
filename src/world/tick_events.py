"""Tick-level change events emitted by world-service.

What's on the wire
──────────────────
A ``TickChangeEvent`` is the notification world-service publishes after each
tick: "as of tick T, these cells changed — come read them via ``WorldView``
if you care." Locations only, not values; the read API is the source of
current truth.

This shape is deliberate (see [[pod-architecture]]):

* Events are notifications, not value carriers. Consumers always re-read
  through ``WorldView`` so they get the latest state, not a snapshot frozen
  at emit time.
* Locations-only keeps the wire payload small and forces the two boundaries
  (event stream vs read API) to do distinct jobs.
* In-process today, iterator-based; same shape ships verbatim across a pod
  boundary later (just swap the sink).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from world.generic_engine import GenericWorldEngine


@dataclass(frozen=True)
class TickChangeEvent:
    """One event per tick. Carries the tick number and the locations of
    cells whose state changed during that tick."""

    tick: int
    changed_cells: tuple[tuple[int, int, int], ...]


def iter_tick_events(
    engine: GenericWorldEngine,
    horizon_ticks: int,
) -> Iterator[TickChangeEvent]:
    """Tick the engine forward and yield one TickChangeEvent per tick.

    For testing: iterate and assert. For production: iterate and send to
    the wire. Same loop, different sink.

    The set of changed cells comes from the physics module's
    ``last_changed_cells`` attribute, which scripted physics populates each
    tick. Modules that don't expose it produce events with an empty set.
    """
    for _ in range(horizon_ticks):
        snapshot = engine.tick()
        changed = getattr(engine.physics, "last_changed_cells", set())
        yield TickChangeEvent(
            tick=snapshot.tick,
            changed_cells=tuple(sorted(changed)),
        )
