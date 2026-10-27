from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Mode(str, Enum):
    METRO = "metro"
    BUS = "bus"
    TRAIN = "train"
    WALK = "walk"


class Leg(BaseModel):
    mode: Mode
    service_id: str = ""
    service_name: str = ""
    from_stop: str
    to_stop: str
    duration_min: float
    fare: float = 0.0
    distance_m: float = 0.0
    is_transfer: bool = False


class Journey(BaseModel):
    legs: list[Leg] = Field(default_factory=list)
    depart_at: str | None = None
    arrive_at: str | None = None
    duration_min: float = 0.0
    fare: float = 0.0
    transfers: int = 0
    walk_m: float = 0.0
    modes: list[Mode] = Field(default_factory=list)
    reliability: float = 1.0
    path_stops: list[str] = Field(default_factory=list)
    live_delay_min: float = 0.0
    score: float | None = None
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)

    @property
    def summary(self) -> str:
        chain = [f"{self.legs[0].from_stop}"]
        for leg in self.legs:
            if leg.mode == Mode.WALK:
                chain.append("Walk")
            else:
                chain.append(leg.service_name)
            chain.append(leg.to_stop)
        return " -> ".join(chain)
