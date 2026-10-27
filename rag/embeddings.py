from __future__ import annotations

import importlib.util
import os

import numpy as np


class TfidfEmbedder:
    name = "tfidf"

    def __init__(self, corpus: list[str]):
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2), stop_words="english", sublinear_tf=True
        )
        self.vectorizer.fit(corpus)

    def embed(self, texts: list[str]) -> np.ndarray:
        matrix = self.vectorizer.transform(texts)
        dense = matrix.toarray().astype("float32")
        norms = np.linalg.norm(dense, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return dense / norms


class SentenceTransformerEmbedder:
    name = "sentence-transformers"

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = self.model.encode(texts, normalize_embeddings=True)
        return np.asarray(vectors, dtype="float32")


def get_embedder(corpus: list[str], name: str | None = None):
    choice = (name or os.getenv("TRANSITAI_EMBEDDER", "auto")).strip().lower()
    if choice in {"auto", "sentence-transformers", "st"}:
        if importlib.util.find_spec("sentence_transformers"):
            try:
                return SentenceTransformerEmbedder()
            except Exception:
                if choice != "auto":
                    raise
    elif choice == "tfidf":
        pass
    else:
        raise ValueError(f"Unknown embedder: {choice}")
    return TfidfEmbedder(corpus)
