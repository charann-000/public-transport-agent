from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypedDict

from agents.evaluation_agent import RouteEvaluationAgent
from agents.intent_agent import IntentAgent
from agents.rag_agent import RAGAgent
from agents.recommendation_agent import RecommendationAgent
from agents.ride_agent import RideAgent
from agents.route_agent import RoutePlanningAgent
from agents.transport_agent import TransportAgent, TransportContext
from models.journey import Journey
from models.route import EvaluatedJourney, JourneyRequest, Recommendation
from rag.retriever import RetrievedChunk


class PlannerState(TypedDict, total=False):
    request: JourneyRequest
    intent_source: str
    transport: TransportContext
    chunks: list[RetrievedChunk]
    journeys: list[Journey]
    relaxed: list[str]
    route_warnings: list[str]
    evaluated: list[EvaluatedJourney]
    recommendation: Recommendation
    rides: list


@dataclass
class PlanOutput:
    request: JourneyRequest
    intent_source: str
    transport: TransportContext
    chunks: list[RetrievedChunk]
    evaluated: list[EvaluatedJourney]
    recommendation: Recommendation
    rides: list = field(default_factory=list)


def _run_steps(request: JourneyRequest, simulate: bool) -> PlanOutput:
    intent = IntentAgent()
    result = intent.extract(request)
    if result.missing:
        raise ValueError(
            "Please provide both an origin and a destination"
            + (f" (missing: {', '.join(result.missing)})" if result.missing else "")
        )
    transport = TransportAgent(simulate=simulate)
    tctx = transport.context(result.request)
    rag = RAGAgent()
    chunks = rag.retrieve(result.request)
    route = RoutePlanningAgent()
    journeys, relaxed, route_warnings = route.generate(tctx, result.request)
    evaluator = RouteEvaluationAgent()
    evaluated = evaluator.evaluate(journeys, result.request) if journeys else []
    if not journeys and not route_warnings:
        route_warnings.append("No route could be generated for this request.")
    ride_agent = RideAgent()
    rides = ride_agent.estimate(tctx.graph, tctx.origin_id, tctx.dest_id)
    return PlanOutput(
        request=result.request,
        intent_source=result.source,
        transport=tctx,
        chunks=chunks,
        evaluated=evaluated,
        recommendation=recommendation,
        rides=rides,
    )


def run_pipeline(request: JourneyRequest, simulate: bool = False) -> PlanOutput:
    try:
        from langgraph.graph import END, StateGraph
    except ImportError:
        return _run_steps(request, simulate)

    intent = IntentAgent()
    rag = RAGAgent()
    route = RoutePlanningAgent()
    evaluator = RouteEvaluationAgent()
    recommender = RecommendationAgent()
    ride_agent = RideAgent()

    def node_intent(state: PlannerState) -> dict:
        result = intent.extract(state["request"])
        if result.missing:
            raise ValueError(
                "Please provide both an origin and a destination"
                + (f" (missing: {', '.join(result.missing)})" if result.missing else "")
            )
        return {"request": result.request, "intent_source": result.source}

    def node_transport(state: PlannerState) -> dict:
        tctx = TransportAgent(simulate=simulate).context(state["request"])
        return {"transport": tctx}

    def node_rag(state: PlannerState) -> dict:
        return {"chunks": rag.retrieve(state["request"])}

    def node_route(state: PlannerState) -> dict:
        journeys, relaxed, warnings = route.generate(state["transport"], state["request"])
        if not journeys and not warnings:
            warnings.append("No route could be generated for this request.")
        return {"journeys": journeys, "relaxed": relaxed, "route_warnings": warnings}

    def node_evaluate(state: PlannerState) -> dict:
        if not state["journeys"]:
            return {"evaluated": []}
        return {"evaluated": evaluator.evaluate(state["journeys"], state["request"])}

    def node_recommend(state: PlannerState) -> dict:
        recommendation = recommender.recommend(
            state.get("evaluated", []),
            state["request"],
            state["transport"],
            state.get("chunks", []),
            state.get("relaxed", []),
            state.get("route_warnings", []),
        )
        rides = ride_agent.estimate(state["transport"].graph, state["transport"].origin_id, state["transport"].dest_id)
        return {"recommendation": recommendation, "rides": rides}

    builder = StateGraph(PlannerState)
    builder.add_node("intent", node_intent)
    builder.add_node("transport", node_transport)
    builder.add_node("rag", node_rag)
    builder.add_node("route", node_route)
    builder.add_node("evaluate", node_evaluate)
    builder.add_node("recommend", node_recommend)
    builder.set_entry_point("intent")
    builder.add_edge("intent", "transport")
    builder.add_edge("intent", "rag")
    builder.add_edge("transport", "route")
    builder.add_edge("rag", "route")
    builder.add_edge("route", "evaluate")
    builder.add_edge("evaluate", "recommend")
    builder.add_edge("recommend", END)
    compiled = builder.compile()
    state = compiled.invoke({"request": request})
    return PlanOutput(
        request=state["request"],
        intent_source=state.get("intent_source", "rules"),
        transport=state["transport"],
        chunks=state.get("chunks", []),
        evaluated=state.get("evaluated", []),
        recommendation=state["recommendation"],
        rides=state.get("rides", []),
    )