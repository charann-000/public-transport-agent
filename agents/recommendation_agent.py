from __future__ import annotations

from agents.transport_agent import TransportContext
from models.preferences import resolve_weights
from models.route import EvaluatedJourney, JourneyRequest, Recommendation
from rag.retriever import RetrievedChunk
from utils.geo import format_distance, format_minutes, format_money

RELAXED_LABELS = {
    "budget": "budget",
    "max transfers": "maximum transfers",
    "max walking": "maximum walking distance",
    "modes": "preferred modes",
    "arrival deadline": "arrival deadline",
}


def _weights_summary(request: JourneyRequest) -> str:
    weights = resolve_weights(request.profile, request.priorities).normalized()
    labels = {
        "time": "time",
        "fare": "cost",
        "transfers": "transfers",
        "walk": "walking",
        "reliability": "reliability",
    }
    parts = []
    for key, label in labels.items():
        share = weights.get(key, 0.0)
        if share >= 0.05:
            parts.append(f"{label} {share * 100:.0f}%")
    return ", ".join(parts)


class RecommendationAgent:
    def recommend(
        self,
        evaluated: list[EvaluatedJourney],
        request: JourneyRequest,
        transport: TransportContext,
        chunks: list[RetrievedChunk] = None,
        relaxed: list[str] = None,
        route_warnings: list[str] = None,
    ) -> Recommendation:
        chunks = chunks or []
        relaxed = relaxed or []
        route_warnings = route_warnings or []
        warnings = list(route_warnings)
        live = transport.live
        if live.source == "simulated":
            warnings.append("Simulated live disruptions were applied to this plan.")
        elif live.source == "live":
            warnings.append(f"Live transit data applied (updated {live.updated_at}).")
        warnings.extend(live.messages)
        warnings = list(dict.fromkeys(warnings))

        graph = transport.graph
        if not evaluated:
            return Recommendation(
                best=None,
                warnings=warnings,
                explanation=(
                    "No feasible journey could be generated for this request. "
                    + ("Constraints were relaxed without success." if relaxed else "")
                ),
            )

        best = evaluated[0]
        alternatives = evaluated[1:]
        names = transport.origin_name, transport.dest_name
        comparisons: list[str] = []

        for rank, item in enumerate(alternatives, start=2):
            alt = item.journey
            phrases: list[str] = []
            time_delta = alt.duration_min - best.journey.duration_min
            fare_delta = alt.fare - best.journey.fare
            transfer_delta = alt.transfers - best.journey.transfers
            walk_delta = alt.walk_m - best.journey.walk_m
            if fare_delta < -0.5:
                phrases.append(f"cheaper by {format_money(abs(fare_delta))}")
            elif time_delta > 1:
                phrases.append(f"takes {format_minutes(time_delta)} longer")
            elif transfer_delta > 0:
                phrases.append(f"adds {transfer_delta} transfer")
            if time_delta < -1:
                phrases.append(f"{format_minutes(abs(time_delta))} faster")
            if transfer_delta < 0:
                phrases.append(f"fewer transfers")
            if walk_delta > 50:
                phrases.append(f"{format_distance(walk_delta)} more walking")
            comparisons.append(
                f"Alternative {rank}: {alt.summary} — "
                + ("; ".join(phrases) if phrases else "a different trade-off")
            )

        constraint_parts: list[str] = []
        fare_ok = request.budget is None or best.journey.fare <= request.budget + 1e-9
        transfer_ok = request.max_transfers is None or best.journey.transfers <= request.max_transfers
        walk_ok = request.max_walk_m is None or best.journey.walk_m <= request.max_walk_m + 1e-9
        deadline_ok = True
        if request.arrival_deadline and request.departure_time:
            from utils.geo import hhmm_to_minutes

            deadline_ok = hhmm_to_minutes(best.journey.arrive_at) <= hhmm_to_minutes(request.arrival_deadline)
        if fare_ok and transfer_ok and walk_ok and deadline_ok:
            constraint_parts.append("satisfies all of your constraints")
        else:
            constraint_parts.append("was accepted after relaxing constraints")

        weights_note = f"under your weights ({_weights_summary(request)})"
        explanation = (
            f"Recommended: {best.journey.summary} from {names[0]} to {names[1]} — "
            f"depart {best.journey.depart_at or '?'}, arrive {best.journey.arrive_at or '?'} "
            f"({format_minutes(best.journey.duration_min)}), "
            f"fare {format_money(best.journey.fare)}, "
            f"{best.journey.transfers} transfer(s), "
            f"{format_distance(best.journey.walk_m)} walking, "
            f"reliability {best.journey.reliability * 100:.0f}%. "
            f"It {constraint_parts[0]} and ranked first (score {best.score:.2f}) {weights_note}."
        )
        if relaxed:
            explanation += (
                " Relaxed: " + ", ".join(RELAXED_LABELS.get(r, r) for r in relaxed) + "."
            )
        for note in best.journey.notes:
            warnings.append("Note: " + note)

        return Recommendation(
            best=best,
            alternatives=alternatives,
            explanation=explanation,
            comparisons=comparisons,
            relaxed=relaxed,
            warnings=warnings,
        )