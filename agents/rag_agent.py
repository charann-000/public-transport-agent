from __future__ import annotations

from agents.base import LLMClient
from models.route import JourneyRequest
from rag.retriever import RetrievedChunk, Retriever, get_retriever


class RAGAgent:
    def __init__(self, retriever: Retriever | None = None):
        self.retriever = retriever

    def queries(self, request: JourneyRequest) -> list[str]:
        queries: list[str] = []
        if request.origin:
            queries.append(f"{request.origin} station interchange information")
        if request.destination:
            queries.append(f"{request.destination} station information")
        if request.budget is not None:
            queries.append("fare rules budget cost per boarding")
        if request.max_transfers is not None:
            queries.append("transfer interchange tips fast interchanges")
        if request.max_walk_m is not None:
            queries.append("accessibility walking distance lifts")
        if request.modes:
            modes = " ".join(m.value for m in request.modes)
            queries.append(f"reliability delays service policies {modes}")
        queries.append("operating hours first and last service frequency")
        return queries[:5]

    def retrieve(self, request: JourneyRequest, k_each: int = 2, cap: int = 6) -> list[RetrievedChunk]:
        retriever = self.retriever or get_retriever()
        results: list[RetrievedChunk] = []
        seen: set[str] = set()
        for query in self.queries(request):
            for item in retriever.search(query, k=k_each):
                if item.chunk.id in seen:
                    continue
                seen.add(item.chunk.id)
                results.append(item)
                if len(results) >= cap:
                    return results
        return results

    @staticmethod
    def context_text(chunks: list[RetrievedChunk], limit: int = 220) -> str:
        parts = []
        for item in chunks:
            snippet = item.chunk.text.strip().replace("\n", " ")
            snippet = snippet[:limit] + ("…" if len(snippet) > limit else "")
            parts.append(f"[{item.chunk.source}] {item.chunk.heading}: {snippet}")
        return "\n\n".join(parts)