"""Cell-state repository — manages the mutable working copy in cell_state.

`cell_state.version` names a group of state. `'seed'` is the immutable
source of truth, written once by the data pipeline. A simulation run works
against its own group (e.g. `'simulation'`), created by copying seed. The
world-service mutates that working copy; the seed is never touched.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from stores.base import CellStateRepository as CellStateRepositoryBase
from stores.postgres.gateway import PgGateway

if TYPE_CHECKING:
    from world.state_snapshot import CellStateSnapshot

logger = logging.getLogger(__name__)

# Mutable cell_state columns the world-service writes back. Terrain-static
# fields (terrain_type, slope) and fields with no cell_state column
# (fire_state, Rothermel metrics) are deliberately excluded.
_WRITEBACK_COLUMNS = (
    "temperature_c",
    "humidity_pct",
    "wind_speed_mps",
    "wind_direction_deg",
    "pressure_hpa",
    "fuel_moisture",
    "fire_intensity",
    "vegetation",
)


class CellStateRepository(CellStateRepositoryBase):
    def __init__(self, pg_gateway: PgGateway):
        self._pg = pg_gateway

    def _remove(self, region: str, version: str) -> int:
        sql = "delete from cell_state where region = %s and version = %s"
        return self._pg.execute(sql, (region, version))

    def _copy_from_seed(self, region: str, version: str, seed_version: str) -> int:
        sql = """
        insert into cell_state (version,
                                grid_row,
                                grid_column,
                                layer,
                                temperature_c,
                                humidity_pct,
                                wind_speed_mps,
                                wind_direction_deg,
                                pressure_hpa,
                                fuel_moisture,
                                fire_intensity,
                                region,
                                vegetation)
        select %s as version,
               grid_row,
               grid_column,
               layer,
               temperature_c,
               humidity_pct,
               wind_speed_mps,
               wind_direction_deg,
               pressure_hpa,
               fuel_moisture,
               fire_intensity,
               region,
               vegetation
        from cell_state
        where region = %s
          and version = %s
        """
        return self._pg.execute(sql, (version, region, seed_version))

    def bootstrap(self, region: str, version: str, seed_version: str = "seed") -> int:
        if version == seed_version:
            raise ValueError(
                f"Refusing to bootstrap onto the seed group {seed_version!r} — "
                "the seed is the immutable source and must not be overwritten."
            )
        deleted = self._remove(region, version)
        inserted = self._copy_from_seed(region, version, seed_version)
        logger.info(
            "Bootstrapped cell_state region=%r version=%r: deleted %d, copied %d from %r",
            region,
            version,
            deleted,
            inserted,
            seed_version,
        )
        return inserted

    def write_state(self, region: str, version: str, snapshots: list[CellStateSnapshot]) -> int:
        if version == "seed":
            raise ValueError("Refusing to write state onto the 'seed' group.")
        if not snapshots:
            return 0

        set_clause = ",\n            ".join(f"{c} = %({c})s" for c in _WRITEBACK_COLUMNS)
        sql = f"""
        update cell_state set
            {set_clause}
        where region      = %(region)s
          and version     = %(version)s
          and grid_row    = %(grid_row)s
          and grid_column = %(grid_column)s
          and layer       = %(layer)s
        """
        params = [
            {
                "region": region,
                "version": version,
                "grid_row": s.grid_row,
                "grid_column": s.grid_column,
                "layer": s.layer,
                **{c: s.state.get(c) for c in _WRITEBACK_COLUMNS},
            }
            for s in snapshots
        ]
        with self._pg.conn() as conn, conn.cursor() as cur:
            cur.executemany(sql, params)
            return cur.rowcount
