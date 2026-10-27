from __future__ import annotations

from dataclasses import dataclass

from utils.geo import haversine_m


@dataclass(frozen=True)
class RideEstimate:
    provider: str
    mode: str
    fare: float
    eta_min: float
    distance_m: float
    surge: float


def _estimate_fare(distance_m: float, base: float, per_km: float, min_fare: float, surge: float = 1.0) -> float:
    km = distance_m / 1000.0
    fare = base + km * per_km
    fare = max(min_fare, fare) * surge
    return round(fare, 2)


def _eta(distance_m: float, speed_kmh: float = 30.0, pickup_min: float = 2.0) -> float:
    travel_min = (distance_m / 1000.0) / speed_kmh * 60.0 if speed_kmh > 0 else pickup_min
    return round(travel_min + pickup_min, 1)


def rapido_estimate(lat1: float, lon1: float, lat2: float, lon2: float, surge: float = 1.0) -> list[RideEstimate]:
    dist = haversine_m(lat1, lon1, lat2, lon2)
    rides = []
    rides.append(RideEstimate(provider="Rapido", mode="Bike", fare=_estimate_fare(dist, 20, 10, 35, surge), eta_min=_eta(dist, 32, 2), distance_m=dist, surge=surge))
    rides.append(RideEstimate(provider="Rapido", mode="Auto", fare=_estimate_fare(dist, 30, 14, 50, surge), eta_min=_eta(dist, 28, 2), distance_m=dist, surge=surge))
    rides.append(RideEstimate(provider="Rapido", mode="Car", fare=_estimate_fare(dist, 45, 16, 70, surge), eta_min=_eta(dist, 25, 2.5), distance_m=dist, surge=surge))
    return rides


def uber_estimate(lat1: float, lon1: float, lat2: float, lon2: float, surge: float = 1.0) -> list[RideEstimate]:
    dist = haversine_m(lat1, lon1, lat2, lon2)
    rides = []
    rides.append(RideEstimate(provider="Uber", mode="Auto", fare=_estimate_fare(dist, 35, 14, 55, surge*1.08), eta_min=_eta(dist, 26, 2.5), distance_m=dist, surge=surge*1.08))
    rides.append(RideEstimate(provider="Uber", mode="Go/Compact", fare=_estimate_fare(dist, 45, 16, 65, surge*1.12), eta_min=_eta(dist, 26, 3), distance_m=dist, surge=surge*1.12))
    rides.append(RideEstimate(provider="Uber", mode="Premier", fare=_estimate_fare(dist, 65, 18, 85, surge*1.18), eta_min=_eta(dist, 24, 3.5), distance_m=dist, surge=surge*1.18))
    return rides
