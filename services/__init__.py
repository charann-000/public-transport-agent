from __future__ import annotations

from functools import lru_cache

from routing.graph import TransitGraph
from services.live_data import LiveStatus, fetch_live
from services.maps_api import build_map
from services.transport_api import load_gtfs_dir, load_network_spec


@lru_cache(maxsize=2)
def get_graph() -> TransitGraph:
    return TransitGraph(load_network_spec())


__all__ = [
    "LiveStatus",
    "TransitGraph",
    "build_map",
    "fetch_live",
    "get_graph",
    "load_gtfs_dir",
    "load_network_spec",
]