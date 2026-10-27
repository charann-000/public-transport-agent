from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Weights:
    time: float
    fare: float
    transfers: float
    walk: float
    reliability: float
    distance: float = 0.0

    @property
    def total(self) -> float:
        return self.time + self.fare + self.transfers + self.walk + self.reliability + self.distance

    def normalized(self) -> dict[str, float]:
        t = self.total or 1.0
        return {
            "time": self.time / t,
            "fare": self.fare / t,
            "transfers": self.transfers / t,
            "walk": self.walk / t,
            "reliability": self.reliability / t,
            "distance": self.distance / t,
        }


PROFILE_WEIGHTS: dict[str, Weights] = {
    "fastest": Weights(1.0, 0.1, 0.2, 0.1, 0.2, 0.2),
    "cheapest": Weights(0.1, 2.0, 0.2, 0.1, 0.2, 0.3),
    "shortest": Weights(0.2, 0.3, 0.2, 0.1, 0.2, 2.0),
    "fewest_transfers": Weights(0.3, 0.2, 2.0, 0.2, 0.2, 0.2),
    "balanced": Weights(0.8, 0.8, 0.6, 0.4, 0.5, 0.6),
    "most_reliable": Weights(0.4, 0.2, 0.2, 0.1, 2.0, 0.2),
}

PRIORITY_ALIASES: dict[str, str] = {
    "time": "time",
    "fastest": "time",
    "quick": "time",
    "speed": "time",
    "cost": "fare",
    "fare": "fare",
    "cheapest": "fare",
    "budget": "fare",
    "transfers": "transfers",
    "changes": "transfers",
    "walk": "walk",
    "walking": "walk",
    "reliability": "reliability",
    "reliable": "reliability",
    "distance": "distance",
    "shortest": "distance",
    "short": "distance",
    "balanced": "balanced",
}

PROFILE_ALIASES: dict[str, str] = {
    "fastest": "fastest",
    "cheapest": "cheapest",
    "shortest": "shortest",
    "fewest transfers": "fewest_transfers",
    "fewest_transfers": "fewest_transfers",
    "balanced": "balanced",
    "most reliable": "most_reliable",
    "most_reliable": "most_reliable",
}


def resolve_weights(profile: str, priorities: list[str]) -> Weights:
    key = PROFILE_ALIASES.get(profile.strip().lower(), "balanced")
    base = PROFILE_WEIGHTS.get(key, PROFILE_WEIGHTS["balanced"])
    values = {
        "time": base.time,
        "fare": base.fare,
        "transfers": base.transfers,
        "walk": base.walk,
        "reliability": base.reliability,
        "distance": base.distance,
    }
    for raw in priorities:
        metric = PRIORITY_ALIASES.get(raw.strip().lower())
        if metric and metric in values:
            values[metric] += 0.8
    return Weights(**values)
