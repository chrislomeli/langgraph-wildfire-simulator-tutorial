"""Cell-state repository — manages the mutable working copy in cell_state.

`cell_state.version` names a group of state. `'seed'` is the immutable
source of truth, written once by the data pipeline. A simulation run works
against its own group (e.g. `'simulation'`), created by copying seed. The
world-service mutates that working copy; the seed is never touched.
"""

from __future__ import annotations

import logging

from stores.base import CellStateRepository as CellStateRepositoryBase
from stores.postgres.gateway import PgGateway

logger = logging.getLogger(__name__)


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
