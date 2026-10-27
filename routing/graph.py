from __future__ import annotations

import copy
import difflib
import json
from dataclasses import dataclass
from pathlib import Path

import networkx as nx

from utils.geo import haversine_m
from utils.texting import match_stop, normalize_name

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DEFAULT_NETWORK_PATH = DATA_DIR / "network.json"
ALIGHT_MIN = 0.25


@dataclass(frozen=True)
class Stop:
    id: str
    name: str
    lat: float
    lon: float


@dataclass(frozen=True)
class Service:
    id: str
    name: str
    mode: str
    reliability: float
    stops: tuple[str, ...]


def at_node(stop_id: str) -> tuple:
    return ("at", stop_id)


def ride_node(service_id: str, board_stop: str, current_stop: str) -> tuple:
    return ("ride", service_id, board_stop, current_stop)


def stop_of_node(node: tuple) -> str:
    return node[1] if node[0] == "at" else node[3]


def load_spec(path: str | Path | None = None) -> dict:
    p = Path(path) if path else DEFAULT_NETWORK_PATH
    return json.loads(p.read_text(encoding="utf-8"))


class TransitGraph:
    def __init__(self, spec: dict, G: nx.DiGraph | None = None):
        self.spec = spec
        self.settings = spec.get("settings", {})
        self.fare_tiers = spec.get("fare_rules", {})
        self.stops = {
            s["id"]: Stop(id=s["id"], name=s["name"], lat=s["lat"], lon=s["lon"])
            for s in spec["stops"]
        }
        self.services = {
            s["id"]: Service(
                id=s["id"],
                name=s["name"],
                mode=s["mode"],
                reliability=float(s.get("reliability", 0.9)),
                stops=tuple(
                    st["stop_id"] if isinstance(st, dict) else (st["id"] if isinstance(st, dict) and "id" in st else str(st))
                    for st in s.get("stops", [])
                ),
            )
            for s in spec["services"]
        }
        self.G = G if G is not None else self._build()

    @property
    def stop_names(self) -> list[str]:
        return [s.name for s in self.stops.values()]

    def stop_name(self, stop_id: str) -> str:
        return self.stops[stop_id].name

    def resolve_stop(self, value: str) -> str | None:
        if not value:
            return None
        name = match_stop(value)
        if name is not None:
            for sid, stop in self.stops.items():
                if normalize_name(stop.name) == normalize_name(name) or stop.name == name:
                    return sid
        target = normalize_name(value)
        if not target:
            return None
        named = {normalize_name(s.name): sid for sid, s in self.stops.items()}
        if target in named:
            return named[target]
        close = difflib.get_close_matches(target, list(named), n=1, cutoff=0.6)
        if close:
            return named[close[0]]
        return None

    def suggest_stops(self, value: str, n: int = 3) -> list[str]:
        target = normalize_name(value)
        named = {normalize_name(s.name): s.name for s in self.stops.values()}
        close = difflib.get_close_matches(target, list(named), n=n, cutoff=0.55)
        return [named[c] for c in close]

    def board_time(self, mode: str) -> float:
        return float(self.settings.get("board_time_min", {}).get(mode, 2.0))

    def segment(self, mode: str, a_id: str, b_id: str) -> tuple[float, float]:
        a, b = self.stops[a_id], self.stops[b_id]
        straight = haversine_m(a.lat, a.lon, b.lat, b.lon)
        factor = float(self.settings.get("road_factor", {}).get(mode, 1.3))
        speed = float(self.settings.get("speed_kmh", {}).get(mode, 20.0))
        dwell = float(self.settings.get("dwell_min", 0.5))
        road_m = straight * factor
        minutes = (road_m / 1000.0) / speed * 60.0 + dwell
        return minutes, road_m

    def walk_time(self, distance_m: float) -> float:
        speed = float(self.settings.get("walk_speed_kmh", 4.5))
        return (distance_m / 1000.0) / speed * 60.0

    def fare_for(self, mode: str, distance_km: float) -> float:
        tiers = self.fare_tiers.get(mode, [[9999, 0]])
        for max_d, fare in tiers:
            if distance_km <= float(max_d):
                return float(fare)
        return float(tiers[-1][1])

    def _build(self) -> nx.DiGraph:
        G = nx.DiGraph()
        G.graph["stop_coords"] = {sid: (s.lat, s.lon) for sid, s in self.stops.items()}
        for link in self.spec.get("walk_links", []):
            a, b = link["from"], link["to"]
            if a not in self.stops or b not in self.stops:
                continue
            dist = float(link["distance_m"])
            minutes = self.walk_time(dist)
            for u, v in ((at_node(a), at_node(b)), (at_node(b), at_node(a))):
                G.add_edge(
                    u, v, kind="walk", time_min=minutes, fare=0.0, walk_m=dist,
                    board=0, mode="walk", service="", dist_m=dist, delay=0.0,
                )
        for svc in self.services.values():
            mode = svc.mode
            stops = list(svc.stops)
            idx = {s: i for i, s in enumerate(stops)}
            for i in range(len(stops) - 1):
                a, b = stops[i], stops[i + 1]
                minutes, road_m = self.segment(mode, a, b)
                for bs in stops:
                    for x, y in ((a, b), (b, a)):
                        G.add_edge(
                            ride_node(svc.id, bs, x), ride_node(svc.id, bs, y),
                            kind="ride", time_min=minutes, fare=0.0, walk_m=0.0,
                            board=0, mode=mode, service=svc.id, dist_m=road_m, delay=0.0,
                        )
            for bs in stops:
                G.add_edge(
                    at_node(bs), ride_node(svc.id, bs, bs),
                    kind="board", time_min=self.board_time(mode), fare=0.0, walk_m=0.0,
                    board=1, mode=mode, service=svc.id, dist_m=0.0, delay=0.0,
                )
                for other in stops:
                    if other == bs:
                        continue
                    # compute distance traveled along service from board stop to alight stop
                    dist_km = 0.0
                    if idx[other] >= idx[bs]:
                        for k in range(idx[bs], idx[other]):
                            a, b = stops[k], stops[k + 1]
                            _, rm = self.segment(mode, a, b)
                            dist_km += rm / 1000.0
                    else:
                        for k in range(idx[bs], idx[other], -1):
                            a, b = stops[k], stops[k - 1]
                            _, rm = self.segment(mode, a, b)
                            dist_km += rm / 1000.0
                    G.add_edge(
                        ride_node(svc.id, bs, other), at_node(other),
                        kind="alight", time_min=ALIGHT_MIN, fare=self.fare_for(mode, dist_km),
                        walk_m=0.0, board=0, mode=mode, service=svc.id, dist_m=dist_km * 1000.0, delay=0.0,
                    )
        return G

    def with_live(self, status) -> "TransitGraph":
        other = copy.copy(self)
        G = self.G.copy()
        for service_id, minutes in getattr(status, "delays", {}).items():
            if service_id not in self.services:
                continue
            for _, _, data in G.edges(data=True):
                if data.get("kind") == "board" and data.get("service") == service_id:
                    data["time_min"] = data.get("time_min", 0.0) + float(minutes)
                    data["delay"] = data.get("delay", 0.0) + float(minutes)
        for entry in getattr(status, "suspended", []):
            service_id, a, b = entry
            if service_id not in self.services or a not in self.stops or b not in self.stops:
                continue
            for bs in self.services[service_id].stops:
                for x, y in ((a, b), (b, a)):
                    u, v = ride_node(service_id, bs, x), ride_node(service_id, bs, y)
                    if G.has_edge(u, v):
                        G.remove_edge(u, v)
        G.graph["live"] = {
            "delays": dict(getattr(status, "delays", {})),
            "suspended": [tuple(e) for e in getattr(status, "suspended", [])],
        }
        other.G = G
        return other


def build_graph(spec: dict | None = None) -> TransitGraph:
    return TransitGraph(spec if spec is not None else load_spec())
