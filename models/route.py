from __future__ import annotations

from pydantic import BaseModel, Field

from models.journey import Journey, Mode


class JourneyRequest(BaseModel):
    origin: str = ""
    destination: str = ""
    text: str | None = None
    departure_time: str | None = None
    arrival_deadline: str | None = None
    budget: float | None = None
    max_transfers: int | None = None
    max_walk_m: float | None = None
    modes: list[Mode] | None = None
    profile: str = "balanced"
    priorities: list[str] = Field(default_factory=lambda: ["balanced"])
    date_note: str | None = None


class IntentResult(BaseModel):
    request: JourneyRequest
    source: str = "rules"
    missing: list[str] = Field(default_factory=list)


class EvaluatedJourney(BaseModel):
    journey: Journey
    score: float = 0.0
    breakdown: dict[str, float] = Field(default_factory=dict)
    feasible: bool = True
    violated: list[str] = Field(default_factory=list)
    relaxed: list[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    best: EvaluatedJourney | None = None
    alternatives: list[EvaluatedJourney] = Field(default_factory=list)
    explanation: str = ""
    comparisons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    relaxed: list[str] = Field(default_factory=list)
