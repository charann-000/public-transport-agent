from __future__ import annotations

import re
import threading
from dataclasses import dataclass

from rag.embeddings import get_embedder
from rag.ingestion import Chunk, ingest
from rag.vector_store import VectorStore

TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass
class RetrievedChunk:
    chunk: Chunk
    score: float


def _tokens(text: str) -> set[str]:
    return set(TOKEN_RE.findall(text.lower()))


class Retriever:
    def __init__(self, chunks: list[Chunk], embedder, store: VectorStore):
        self.chunks = chunks
        self.embedder = embedder
        self.store = store

    @classmethod
    def build(cls) -> "Retriever":
        chunks = ingest()
        if not chunks:
            return cls([], None, VectorStore(1))
        corpus = [f"{c.heading}. {c.text}" for c in chunks]
        embedder = get_embedder(corpus)
        vectors = embedder.embed(corpus)
        store = VectorStore(vectors.shape[1])
        store.add(vectors)
        return cls(chunks, embedder, store)

    def search(self, query: str, k: int = 4) -> list[RetrievedChunk]:
        if not self.chunks or self.embedder is None:
            return []
        query_vec = self.embedder.embed([query])[0]
        hits = self.store.search(query_vec, k=max(k * 3, 9))
        query_tokens = _tokens(query)
        scored: list[RetrievedChunk] = []
        for idx, cosine in hits:
            chunk = self.chunks[idx]
            overlap = _tokens(f"{chunk.heading} {chunk.text}")
            if query_tokens:
                jaccard = len(query_tokens & overlap) / len(query_tokens)
            else:
                jaccard = 0.0
            scored.append(RetrievedChunk(chunk=chunk, score=0.75 * cosine + 0.25 * jaccard))
        scored.sort(key=lambda r: -r.score)
        seen: set[str] = set()
        results: list[RetrievedChunk] = []
        for item in scored:
            if item.chunk.id in seen:
                continue
            seen.add(item.chunk.id)
            results.append(item)
            if len(results) >= k:
                break
        return results


_retriever: Retriever | None = None
_build_lock = threading.Lock()


def get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        with _build_lock:
            if _retriever is None:
                _retriever = Retriever.build()
    return _retriever
