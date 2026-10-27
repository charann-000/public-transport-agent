from __future__ import annotations

import heapq
import math
from collections.abc import Callable

import networkx as nx

from routing.graph import stop_of_node

MIN_MIN_PER_KM = 1.6


def time_heuristic(G: nx.DiGraph, target_stop: str, min_min_per_km: float = MIN_MIN_PER_KM) -> Callable[[tuple], float]:
    coords = G.graph.get("stop_coords", {})

    def h(node: tuple) -> float:
        stop_id = stop_of_node(node)
        if stop_id == target_stop:
            return 0.0
        a = coords.get(stop_id)
        b = coords.get(target_stop)
        if not a or not b:
            return 0.0
        from utils.geo import haversine_m

        return haversine_m(a[0], a[1], b[0], b[1]) / 1000.0 * min_min_per_km

    return h


def astar(
    G: nx.DiGraph,
    source,
    target,
    heuristic: Callable[[tuple], float] | None = None,
    weight: str | Callable[[str, str, dict], float] = "weight",
) -> tuple[list | None, float, int]:
    if source == target:
        return [source], 0.0, 0
    if callable(weight):
        fn = weight
    else:
        key = weight

        def fn(u, v, data):
            return float(data.get(key, 1.0))

    h = heuristic or (lambda node: 0.0)
    g = {source: 0.0}
    prev: dict = {}
    visited: set = set()
    heap: list = [(h(source), 0, source)]
    counter = 1
    expanded = 0
    while heap:
        f, _, u = heapq.heappop(heap)
        if u in visited:
            continue
        visited.add(u)
        expanded += 1
        if u == target:
            break
        for v, data in G[u].items():
            if v in visited:
                continue
            ng = g[u] + fn(u, v, data)
            if ng < g.get(v, math.inf) - 1e-12:
                g[v] = ng
                prev[v] = u
                heapq.heappush(heap, (ng + h(v), counter, v))
                counter += 1
    if target not in g:
        return None, math.inf, expanded
    path = [target]
    while path[-1] != source:
        path.append(prev[path[-1]])
    path.reverse()
    return path, g[target], expanded
