from __future__ import annotations

from models.route import JourneyRequest
from routing.graph import TransitGraph
from services.ride_share import rapido_estimate, uber_estimate


class RideAgent:
    def estimate(self, graph: TransitGraph, origin_id: str, dest_id: str) -> list:
        o = graph.stops[origin_id]
        d = graph.stops[dest_id]
        rides = []
        rides.extend(rapido_estimate(o.lat, o.lon, d.lat, d.lon, surge=1.0))
        rides.extend(uber_estimate(o.lat, o.lon, d.lat, d.lon, surge=1.1))
        rides.sort(key=lambda r: r.fare)
        return rides
