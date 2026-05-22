from datetime import datetime

from pydantic import BaseModel


class UpdatedCell(BaseModel):
    row: int
    col: int
    layer: int


class AdvisoryRequest(BaseModel):
    id: str
    region: str
    version: str
    tick: int
    timestamp: datetime
    cells: list[UpdatedCell]
