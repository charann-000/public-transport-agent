from __future__ import annotations

import numpy as np


class VectorStore:
    def __init__(self, dim: int):
        self.dim = dim
        self._faiss = None
        self._vectors: list[np.ndarray] = []
        try:
            import faiss

            self._faiss = faiss.IndexFlatIP(dim)
        except ImportError:
            self._faiss = None

    def __len__(self) -> int:
        if self._faiss is not None:
            return self._faiss.ntotal
        return len(self._vectors)

    def add(self, vectors: np.ndarray) -> None:
        vectors = np.ascontiguousarray(vectors, dtype="float32")
        if self._faiss is not None:
            self._faiss.add(vectors)
        else:
            for row in vectors:
                self._vectors.append(row)

    def search(self, query: np.ndarray, k: int = 4) -> list[tuple[int, float]]:
        if len(self) == 0:
            return []
        query = np.ascontiguousarray(query.reshape(1, -1), dtype="float32")
        k = min(k, len(self))
        if self._faiss is not None:
            scores, indexes = self._faiss.search(query, k)
            return [
                (int(idx), float(score))
                for idx, score in zip(indexes[0], scores[0])
                if idx >= 0
            ]
        matrix = np.vstack(self._vectors)
        scores = matrix @ query[0]
        order = np.argsort(-scores)[:k]
        return [(int(i), float(scores[i])) for i in order]
