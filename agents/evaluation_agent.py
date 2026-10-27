from __future__ import annotations

from models.journey import Journey
from models.preferences import resolve_weights
from models.route import EvaluatedJourney, JourneyRequest
from routing.optimizer import score_journeys


class RouteEvaluationAgent:
    def evaluate(
        self, journeys: list[Journey], request: JourneyRequest, k: int = 5
    ) -> list[EvaluatedJourney]:
        weights = resolve_weights(request.profile, request.priorities)
        scored = score_journeys(journeys, weights)
        return scored[:k]