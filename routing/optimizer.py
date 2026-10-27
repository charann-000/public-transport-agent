from __future__ import annotations

import math
from collections import deque

from models.journey import Journey, Leg, Mode
from models.preferences import Weights, resolve_weights
from models.route import EvaluatedJourney, JourneyRequest
from routing.astar import astar, time_heuristic
from routing.dijkstra import dijkstra
from routing.graph import (
    ALIGHT_MIN,
    TransitGraph,
    at_node,
    ride_node,
    stop_of_node,
)
from utils.geo import hhmm_to_minutes, minutes_to_hhmm

SEARCH_PROFILES: dict[str, dict[str, float]] = {
    "fastest": {"time": 1.0, "fare": 0.0, "transfers": 0.0, "walk": 0.0},
    "cheapest": {"time": 0.2, "fare": 1.0, "transfers": 0.1, "walk": 0.0},
    "fewest_transfers": {"time": 0.35, "fare": 0.15, "transfers": 1.0, "walk": 0.1},
    "least_walking": {"time": 0.3, "fare": 0.1, "transfers": 0.2, "walk": 1.0},
    "balanced": {"time": 0.7, "fare": 0.7, "transfers": 0.6, "walk": 0.4},
}
FARE_TO_MIN = 0.5
TRANSFER_EQ_MIN = 8.0
WALK_MIN_PER_M = 0.02
DEFAULT_DEPARTURE = "08:00"


def _profile_weight(profile: dict[str, float]):
    def w(u, v, data):
        return (
            profile.get("time", 0.0) * float(data.get("time_min", 0.0))
            + profile.get("fare", 0.0) * float(data.get("fare", 0.0)) * FARE_TO_MIN
            + profile.get("transfers", 0.0) * float(data.get("board", 0)) * TRANSFER_EQ_MIN
            + profile.get("walk", 0.0) * float(data.get("walk_m", 0.0)) * WALK_MIN_PER_M
        )

    return w


def _time_weight(u, v, data):
    return float(data.get("time_min", 0.0))


def _criteria(data) -> tuple[float, float, float, float]:
    return (
        float(data.get("time_min", 0.0)),
        float(data.get("fare", 0.0)),
        float(data.get("board", 0)),
        float(data.get("walk_m", 0.0)),
    )


def _dominates(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    return all(x <= y + 1e-9 for x, y in zip(a, b)) and any(
        x < y - 1e-9 for x, y in zip(a, b)
    )


def pareto_paths(G, source, target, max_labels: int = 6000, max_paths: int = 30) -> list[list]:
    all_labels: list[tuple] = [(source, (0.0, 0.0, 0.0, 0.0), -1)]
    node_labels: dict = {source: [((0.0, 0.0, 0.0, 0.0), 0)]}
    queue: deque[int] = deque([0])
    while queue and len(all_labels) < max_labels:
        idx = queue.popleft()
        node, crit, _ = all_labels[idx]
        active = node_labels.get(node, [])
        if not any(label_idx == idx for _, label_idx in active):
            continue
        if node == target:
            continue
        for v, data in G[node].items():
            tc, fc, bc, wc = _criteria(data)
            nc = (crit[0] + tc, crit[1] + fc, crit[2] + bc, crit[3] + wc)
            existing = node_labels.setdefault(v, [])
            if any(_dominates(existing_crit, nc) for existing_crit, _ in existing):
                continue
            existing[:] = [
                (existing_crit, existing_idx)
                for existing_crit, existing_idx in existing
                if not _dominates(nc, existing_crit)
            ]
            new_idx = len(all_labels)
            all_labels.append((v, nc, idx))
            existing.append((nc, new_idx))
            queue.append(new_idx)
    dest_labels = node_labels.get(target, [])
    ranked = sorted(dest_labels, key=lambda item: item[0][0])
    paths: list[list] = []
    for _, idx in ranked:
        chain = []
        while idx != -1:
            node, _, prev = all_labels[idx]
            chain.append(node)
            idx = prev
        chain.reverse()
        if chain and chain not in paths:
            paths.append(chain)
        if len(paths) >= max_paths:
            break
    return paths


def candidate_paths(graph: TransitGraph, origin_id: str, dest_id: str) -> list[list]:
    G = graph.G
    source, target = at_node(origin_id), at_node(dest_id)
    raw: list[list] = []
    for profile in SEARCH_PROFILES.values():
        path, _ = dijkstra(G, source, target, weight=_profile_weight(profile))
        if path:
            raw.append(path)
    path, _, _ = astar(G, source, target, heuristic=time_heuristic(G, dest_id), weight=_time_weight)
    if path:
        raw.append(path)
    raw.extend(pareto_paths(G, source, target))
    seen: set[tuple] = set()
    unique: list[list] = []
    for path in raw:
        key = tuple(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def journey_from_path(graph: TransitGraph, nodes: list) -> Journey | None:
    if len(nodes) < 2:
        return None
    G = graph.G
    legs: list[Leg] = []
    board_stop: str | None = None
    service = None
    acc_time = 0.0
    acc_dist = 0.0
    acc_delay = 0.0
    total_delay = 0.0
    for u, v in zip(nodes, nodes[1:]):
        data = G.get_edge_data(u, v)
        if data is None:
            return None
        kind = data.get("kind")
        if kind == "walk":
            legs.append(
                Leg(
                    mode=Mode.WALK,
                    from_stop=u[1],
                    to_stop=v[1],
                    duration_min=float(data["time_min"]),
                    fare=0.0,
                    distance_m=float(data["walk_m"]),
                )
            )
        elif kind == "board":
            board_stop = u[1]
            service = graph.services.get(data["service"])
            if service is None:
                return None
            acc_time = float(data["time_min"])
            acc_dist = 0.0
            acc_delay = float(data.get("delay", 0.0))
            total_delay += acc_delay
        elif kind == "ride":
            acc_time += float(data["time_min"])
            acc_dist += float(data.get("dist_m", 0.0))
        elif kind == "alight":
            if board_stop is None or service is None:
                return None
            acc_time += float(data["time_min"])
            legs.append(
                Leg(
                    mode=Mode(service.mode),
                    service_id=service.id,
                    service_name=service.name,
                    from_stop=board_stop,
                    to_stop=v[1],
                    duration_min=acc_time,
                    fare=float(data["fare"]),
                    distance_m=acc_dist,
                    is_transfer=len([l for l in legs if l.mode != Mode.WALK]) > 0,
                )
            )
            board_stop = None
            service = None
    ride_legs = [l for l in legs if l.mode != Mode.WALK]
    if not ride_legs and not legs:
        return None
    modes: list[Mode] = []
    for leg in legs:
        if leg.mode not in modes:
            modes.append(leg.mode)
    walk_m = sum(l.distance_m for l in legs if l.mode == Mode.WALK)
    duration = sum(l.duration_min for l in legs)
    fare = sum(l.fare for l in legs)
    if ride_legs:
        total_leg_time = sum(l.duration_min for l in ride_legs)
        reliability = sum(
            graph.services[l.service_id].reliability * l.duration_min for l in ride_legs
        ) / (total_leg_time or 1.0)
    else:
        reliability = 1.0
    path_stops: list[str] = []
    for leg in legs:
        if not path_stops:
            path_stops.append(leg.from_stop)
        if leg.mode == Mode.WALK:
            path_stops.append(leg.to_stop)
        else:
            svc = graph.services[leg.service_id]
            stops = list(svc.stops)
            ib, it = stops.index(leg.from_stop), stops.index(leg.to_stop)
            step = 1 if it > ib else -1
            for i in range(ib + step, it + step, step):
                path_stops.append(stops[i])
    return Journey(
        legs=legs,
        duration_min=duration,
        fare=fare,
        transfers=max(0, len(ride_legs) - 1),
        walk_m=walk_m,
        modes=modes,
        reliability=reliability,
        path_stops=path_stops,
        live_delay_min=total_delay,
    )


def timing(journey: Journey, request: JourneyRequest) -> tuple[int, int, list[str]]:
    notes: list[str] = []
    duration = journey.duration_min
    deadline = None
    if request.arrival_deadline:
        try:
            deadline = hhmm_to_minutes(request.arrival_deadline)
        except ValueError:
            deadline = None
    if request.departure_time:
        try:
            depart = hhmm_to_minutes(request.departure_time)
        except ValueError:
            depart = hhmm_to_minutes(DEFAULT_DEPARTURE)
            notes.append(f"Unreadable departure time; assuming {DEFAULT_DEPARTURE}")
    elif deadline is not None:
        depart = deadline - duration
    else:
        depart = hhmm_to_minutes(DEFAULT_DEPARTURE)
    arrive = depart + duration
    if depart < 0:
        notes.append("Journey would have to start before 00:00 to meet the deadline")
    elif depart < 360:
        notes.append("Departs before 06:00; check first-service times")
    elif arrive > 1380:
        notes.append("Arrives after 23:00; check last-service times")
    return depart, arrive, notes


def assign_times(journey: Journey, request: JourneyRequest) -> None:
    depart, arrive, notes = timing(journey, request)
    journey.depart_at = minutes_to_hhmm(depart) if depart >= 0 else None
    journey.arrive_at = minutes_to_hhmm(arrive % (24 * 60)) if arrive >= 0 else None
    for note in notes:
        if note not in journey.notes:
            journey.notes.append(note)


def _loosened_violations(
    journey: Journey, request: JourneyRequest, level: int
) -> list[str]:
    violated: list[str] = []
    budget = request.budget
    if budget is not None and level >= 1:
        budget = budget * (1 + 0.35 * level)
    if budget is not None and journey.fare > budget + 1e-9:
        violated.append("budget")
    max_transfers = request.max_transfers
    if max_transfers is not None and level >= 2:
        max_transfers = max_transfers + (level - 1)
    if max_transfers is not None and journey.transfers > max_transfers:
        violated.append("max transfers")
    max_walk = request.max_walk_m
    if max_walk is not None and level >= 3:
        max_walk = max_walk + 500 * (level - 2)
    if max_walk is not None and journey.walk_m > max_walk + 1e-9:
        violated.append("max walking")
    if request.modes and level < 4:
        allowed = {m.value for m in request.modes} | {"walk"}
        used = {m.value for m in journey.modes}
        if not used.issubset(allowed):
            violated.append("modes")
    if request.arrival_deadline:
        _, arrive, _ = timing(journey, request)
        try:
            deadline = hhmm_to_minutes(request.arrival_deadline)
        except ValueError:
            deadline = None
        if deadline is not None and arrive > deadline:
            violated.append("arrival deadline")
    return violated


def strict_violations(journey: Journey, request: JourneyRequest) -> list[str]:
    return _loosened_violations(journey, request, 0)


def validate_journey(
    graph: TransitGraph,
    journey: Journey,
    origin_id: str | None = None,
    dest_id: str | None = None,
) -> list[str]:
    errors: list[str] = []
    if not journey.legs:
        return ["journey has no legs"]
    if origin_id and journey.legs[0].from_stop != origin_id:
        errors.append("first leg does not start at the origin")
    if dest_id and journey.legs[-1].to_stop != dest_id:
        errors.append("last leg does not end at the destination")
    G = graph.G
    total_time = total_fare = total_walk = 0.0
    ride_count = 0
    for i, leg in enumerate(journey.legs):
        if i > 0 and journey.legs[i - 1].to_stop != leg.from_stop:
            errors.append(f"legs are not connected at {leg.from_stop}")
        if leg.mode == Mode.WALK:
            data = G.get_edge_data(at_node(leg.from_stop), at_node(leg.to_stop))
            if not data or data.get("kind") != "walk":
                errors.append(f"walk link {leg.from_stop}->{leg.to_stop} does not exist")
            else:
                if abs(float(data["time_min"]) - leg.duration_min) > 0.05:
                    errors.append(f"walk duration mismatch on {leg.from_stop}->{leg.to_stop}")
                if abs(float(data["walk_m"]) - leg.distance_m) > 1.0:
                    errors.append(f"walk distance mismatch on {leg.from_stop}->{leg.to_stop}")
            total_time += leg.duration_min
            total_walk += leg.distance_m
            continue
        svc = graph.services.get(leg.service_id)
        if svc is None:
            errors.append(f"unknown service {leg.service_id}")
            continue
        if leg.mode.value != svc.mode:
            errors.append(f"mode mismatch on {leg.service_id}")
        stops = list(svc.stops)
        if leg.from_stop not in stops or leg.to_stop not in stops:
            errors.append(f"stops not served by {svc.name}")
            continue
        ib, it = stops.index(leg.from_stop), stops.index(leg.to_stop)
        if ib == it:
            errors.append(f"zero-length ride on {svc.name}")
            continue
        step = 1 if it > ib else -1
        if not G.has_edge(at_node(leg.from_stop), ride_node(svc.id, leg.from_stop, leg.from_stop)):
            errors.append(f"cannot board {svc.name} at {leg.from_stop}")
        expected_time = graph.board_time(svc.mode)
        expected_dist = 0.0
        for i in range(ib, it, step):
            u = ride_node(svc.id, leg.from_stop, stops[i])
            v = ride_node(svc.id, leg.from_stop, stops[i + step])
            if not G.has_edge(u, v):
                errors.append(f"missing ride segment {stops[i]}->{stops[i + step]} on {svc.name}")
            m, d = graph.segment(svc.mode, stops[i], stops[i + step])
            expected_time += m
            expected_dist += d
        expected_time += ALIGHT_MIN
        # compute distance for fare
        exp_dist_km = 0.0
        for i in range(ib, it, step):
            _, rm = graph.segment(svc.mode, stops[i], stops[i + step])
            exp_dist_km += rm / 1000.0
        expected_fare = graph.fare_for(svc.mode, exp_dist_km)
        if not G.has_edge(ride_node(svc.id, leg.from_stop, leg.to_stop), at_node(leg.to_stop)):
            errors.append(f"cannot alight {svc.name} at {leg.to_stop}")
        if abs(expected_time - leg.duration_min) > 0.05:
            errors.append(f"ride duration mismatch on {leg.service_name}")
        if abs(expected_fare - leg.fare) > 1e-6:
            errors.append(f"fare mismatch on {leg.service_name}")
        if abs(expected_dist - leg.distance_m) > 1.5:
            errors.append(f"distance mismatch on {leg.service_name}")
        total_time += leg.duration_min
        total_fare += leg.fare
        ride_count += 1
    if abs(total_time - journey.duration_min) > 0.02:
        errors.append("total duration does not match legs")
    if abs(total_fare - journey.fare) > 1e-6:
        errors.append("total fare does not match legs")
    if abs(total_walk - journey.walk_m) > 1.0:
        errors.append("total walking does not match legs")
    expected_transfers = max(0, ride_count - 1)
    if journey.transfers != expected_transfers:
        errors.append("transfer count does not match legs")
    return errors


def score_journeys(journeys: list[Journey], weights: Weights) -> list[EvaluatedJourney]:
    if not journeys:
        return []
    times = [j.duration_min for j in journeys]
    fares = [j.fare for j in journeys]
    transfers = [j.transfers for j in journeys]
    walks = [j.walk_m for j in journeys]

    def norm(value: float, values: list[float]) -> float:
        lo, hi = min(values), max(values)
        if hi - lo < 1e-9:
            return 0.0
        return (value - lo) / (hi - lo)

    distances = [sum(l.distance_m for l in j.legs) for j in journeys]
    w = weights.normalized()
    evaluated: list[EvaluatedJourney] = []
    for j in journeys:
        total_d = sum(l.distance_m for l in j.legs)
        penalties = {
            "time": norm(j.duration_min, times),
            "fare": norm(j.fare, fares),
            "transfers": norm(float(j.transfers), [float(t) for t in transfers]),
            "walk": norm(j.walk_m, walks),
            "reliability": max(0.0, min(1.0, 1.0 - j.reliability)),
            "distance": norm(total_d, distances) if w.get("distance", 0.0) > 0 else 0.0,
        }
        score = 1.0 - sum(w.get(k, 0.0) * v for k, v in penalties.items())
        score = max(0.0, min(1.0, score))
        breakdown = {f"{k}_penalty": round(v, 4) for k, v in penalties.items()}
        breakdown["score"] = round(score, 4)
        evaluated.append(EvaluatedJourney(journey=j, score=score, breakdown=breakdown))
    evaluated.sort(key=lambda e: (-e.score, e.journey.duration_min, e.journey.fare))
    return evaluated


def plan_journeys(
    graph: TransitGraph,
    origin_id: str,
    dest_id: str,
    request: JourneyRequest,
) -> tuple[list[Journey], list[str], list[str]]:
    warnings: list[str] = []
    if origin_id == dest_id:
        raise ValueError("Origin and destination resolve to the same stop.")
    paths = candidate_paths(graph, origin_id, dest_id)
    if not paths:
        return [], [], ["No path exists between these stops on the transport graph."]
    journeys: list[Journey] = []
    for path in paths:
        journey = journey_from_path(graph, path)
        if journey is None:
            continue
        errors = validate_journey(graph, journey, origin_id, dest_id)
        if errors:
            warnings.append("Dropped an invalid candidate: " + "; ".join(errors[:3]))
            continue
        assign_times(journey, request)
        journeys.append(journey)
    if not journeys:
        return [], [], ["Routing produced no valid journeys."]
    relaxed_fields: list[str] = []
    selected: list[Journey] = []
    for level in range(0, 5):
        selected = [j for j in journeys if not _loosened_violations(j, request, level)]
        if selected:
            if level > 0:
                strict_union: set[str] = set()
                for j in selected:
                    strict_union.update(strict_violations(j, request))
                relaxed_fields = sorted(strict_union)
            break
    if not selected:
        return (
            [],
            [],
            [
                "No route satisfies the constraints even after controlled relaxation. "
                "Try raising the budget, allowing more transfers, or permitting more walking."
            ],
        )
    if not relaxed_fields:
        reasons: set[str] = set()
        for j in journeys:
            if j not in selected:
                reasons.update(strict_violations(j, request))
        if reasons:
            warnings.append(
                "Excluded "
                + str(len(journeys) - len(selected))
                + " candidate(s) violating: "
                + ", ".join(sorted(reasons))
            )
    return selected, relaxed_fields, warnings
