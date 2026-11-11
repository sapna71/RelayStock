from typing import Literal
from pydantic import BaseModel


class HealthOut(BaseModel):
    status: Literal["ok"]
    service: str
    environment: str


class ReadyOut(BaseModel):
    status: Literal["ready", "unavailable"]
    database: Literal["ok", "error"]