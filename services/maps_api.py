from __future__ import annotations

import folium

from models.journey import Mode
from models.route import EvaluatedJourney
from routing.graph import TransitGraph
from utils.geo import format_minutes, format_money

MODE_COLOR = {
    "metro": "#3b82f6",
    "bus": "#f59e0b",
    "train": "#10b981",
    "walk": "#6b7280",
}
MODE_LABEL = {
    "metro": "Metro",
    "bus": "Bus",
    "train": "Train",
    "walk": "Walk",
}


def build_map(
    graph: TransitGraph,
    origin_id: str,
    dest_id: str,
    evaluated: list[EvaluatedJourney],
    max_journeys: int = 4,
) -> folium.Map:
    points = [(s.lat, s.lon) for s in graph.stops.values()]
    if not points:
        return folium.Map(location=[17.42, 78.47], zoom_start=11)
    lat = sum(p[0] for p in points) / len(points)
    lon = sum(p[1] for p in points) / len(points)
    m = folium.Map(location=[lat, lon], zoom_start=12)
    origin = graph.stops[origin_id]
    folium.Marker(
        [origin.lat, origin.lon],
        popup=f"<b>From:</b> {origin.name}",
        icon=folium.Icon(color="green", icon="play"),
    ).add_to(m)
    dest = graph.stops[dest_id]
    folium.Marker(
        [dest.lat, dest.lon],
        popup=f"<b>To:</b> {dest.name}",
        icon=folium.Icon(color="red", icon="flag"),
    ).add_to(m)

    for rank, item in enumerate(evaluated[:max_journeys]):
        journey = item.journey
        if rank == 0:
            for leg in journey.legs:
                start = journey.path_stops.index(leg.from_stop)
                end = journey.path_stops.index(leg.to_stop)
                points_line = [
                    (graph.stops[sid].lat, graph.stops[sid].lon)
                    for sid in journey.path_stops[start : end + 1]
                ]
                folium.PolyLine(
                    points_line,
                    color=MODE_COLOR[leg.mode.value],
                    weight=5,
                    opacity=0.9,
                    tooltip=f"{MODE_LABEL[leg.mode.value]} · {leg.service_name or 'walk'}",
                ).add_to(m)
            for leg in journey.legs:
                if leg.mode == Mode.WALK:
                    continue
                stop = graph.stops[leg.from_stop]
                folium.CircleMarker(
                    [stop.lat, stop.lon],
                    radius=5,
                    color="#111827",
                    weight=1,
                    fill=True,
                    fill_color="#ffffff",
                    fill_opacity=1,
                    popup=f"Transfer/hub: {stop.name}",
                ).add_to(m)
        else:
            points_line = [
                (graph.stops[sid].lat, graph.stops[sid].lon)
                for sid in journey.path_stops
            ]
            folium.PolyLine(
                points_line,
                color="#9ca3af",
                weight=3,
                opacity=0.55,
                dash_array="5,6",
                tooltip=f"Alternative {rank}: {format_minutes(journey.duration_min)}, {format_money(journey.fare)}",
            ).add_to(m)
    return m