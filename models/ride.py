from __future__ import annotations

from pydantic import BaseModel


class RideEstimate(BaseModel):
    provider: str
    mode: str
    fare: float
    eta_min: float
    distance_m: float
    surge: float
