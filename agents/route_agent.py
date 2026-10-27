from __future__ import annotations

from agents.transport_agent import TransportContext
from models.journey import Journey
from models.route import JourneyRequest
from routing.optimizer import plan_journeys


class RoutePlanningAgent:
    def generate(
        self, transport: TransportContext, request: JourneyRequest
    ) -> tuple[list[Journey], list[str], list[str]]:
        return plan_journeys(
            transport.graph, transport.origin_id, transport.dest_id, request
        )