"""Per-tick cell-state snapshots.

After each tick the engine appends one ``CellStateSnapshot`` per cell to its
``state_snapshot_log``. The log is the record you would replay against the
database to bring ``cell_state`` rows in sync with the in-memory grid:

    UPDATE cell_state
       SET temperature_c = %(temperature_c)s,
           humidity_pct  = %(humidity_pct)s,
           ...
     WHERE region      = %(region)s
       AND version     = %(version)s
       AND grid_row    = %(grid_row)s
       AND grid_column = %(grid_column)s
       AND layer       = %(layer)s

Full-state, not diffs, by deliberate choice — keeps writeback trivial and
the log self-contained for any tick.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CellStateSnapshot:
    tick: int
    grid_row: int
    grid_column: int
    layer: int
    state: dict[str, Any]
