from __future__ import annotations

from dataclasses import dataclass

from agents.base import LLMClient
from models.route import JourneyRequest
from routing.graph import TransitGraph
from services import get_graph
from services.live_data import LiveStatus, fetch_live


class StopNotFoundError(ValueError):
    def __init__(self, value: str, suggestions: list[str]):
        self.value = value
        self.suggestions = suggestions
        prefix = f'"{value}" could not be matched to a stop.'
        if suggestions:
            prefix += " Did you mean: " + ", ".join(f'"{s}"' for s in suggestions) + "?"
        super().__init__(prefix)


@dataclass
class TransportContext:
    graph: TransitGraph
    origin_id: str
    dest_id: str
    origin_name: str
    dest_name: str
    live: LiveStatus


class TransportAgent:
    def __init__(self, simulate: bool = False):
        self.simulate = simulate

    def context(self, request: JourneyRequest) -> TransportContext:
        if not request.origin:
            raise ValueError("Origin is required.")
        if not request.destination:
            raise ValueError("Destination is required.")
        graph = get_graph()
        origin_id = graph.resolve_stop(request.origin)
        dest_id = graph.resolve_stop(request.destination)
        if origin_id is None:
            raise StopNotFoundError(request.origin, graph.suggest_stops(request.origin))
        if dest_id is None:
            raise StopNotFoundError(
                request.destination, graph.suggest_stops(request.destination)
            )
        live = fetch_live(simulate=self.simulate)
        applied = graph.with_live(live)
        return TransportContext(
            graph=applied,
            origin_id=origin_id,
            dest_id=dest_id,
            origin_name=graph.stop_name(origin_id),
            dest_name=graph.stop_name(dest_id),
            live=live,
        )
