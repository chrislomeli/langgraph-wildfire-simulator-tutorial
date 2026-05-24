"""
world-simulator.agents.logistics.tools.wildfires

Tool: get_wildfire_activity
───────────────────────────
Returns historical wildfire data filtered by acreage range.

Useful for logistics planning: "how many resources were deployed to
fires of similar size?" The agent queries past incidents to estimate
the scale of response needed for a new ignition.

Design notes
────────────
Thin query layer over the wildfire_activity table. The LLM specifies
acreage bounds to find comparable fires. Results include resource
counts (personnel, crews, engines, helicopters) deployed historically.
"""

from __future__ import annotations

from langchain_core.tools import tool

from agents.commons.schemas import Colors, EvaluationCell
from world import GenericWorldEngine

# ═══════════════════════════════════════════════════════════════════════════════
# Tool factory
# ═══════════════════════════════════════════════════════════════════════════════


def make_get_sectors(world_engine: GenericWorldEngine):
    """Factory: closes over the world engine so the LLM only sees the query parameters."""

    @tool
    def get_get_sectors(cells: list[tuple[int, int]]) -> list[str]:
        """Get the cells requested from the caller"""
        print(f"\n{Colors.TEAL}● TOOL get_get_sectors ={cells} {Colors.RESET}")

        sectors = world_engine.get_sector(cells)
        selected_cells = [
            EvaluationCell(
                row=cell.row,
                col=cell.col,
                layer=cell.layer,
                state=cell.cell_state,
                attributes=cell.attributes,
            ).model_dump_json()
            for cell in sectors
        ]
        return selected_cells

    return get_get_sectors
