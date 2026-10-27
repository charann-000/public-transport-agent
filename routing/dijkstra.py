from __future__ import annotations

import heapq
import math
from collections.abc import Callable

import networkx as nx

WeightFn = Callable[[str, str, dict], float]


def _as_weight(weight: str | WeightFn) -> WeightFn:
    if callable(weight):
        return weight
    key = weight

    def w(u, v, data):
        return float(data.get(key, 1.0))

    return w


def dijkstra(
    G: nx.DiGraph,
    source,
    target,
    weight: str | WeightFn = "weight",
) -> tuple[list | None, float]:
    if source == target:
        return [source], 0.0
    fn = _as_weight(weight)
    dist = {source: 0.0}
    prev: dict = {}
    visited: set = set()
    heap: list = [(0.0, 0, source)]
    counter = 1
    while heap:
        d, _, u = heapq.heappop(heap)
        if u in visited:
            continue
        visited.add(u)
        if u == target:
            break
        for v, data in G[u].items():
            if v in visited:
                continue
            nd = d + fn(u, v, data)
            if nd < dist.get(v, math.inf) - 1e-12:
                dist[v] = nd
                prev[v] = u
                heapq.heappush(heap, (nd, counter, v))
                counter += 1
    if target not in dist:
        return None, math.inf
    path = [target]
    while path[-1] != source:
        path.append(prev[path[-1]])
    path.reverse()
    return path, dist[target]
