"""Embedders behind a small protocol. Default: local fastembed. Tests inject a stub."""

from typing import Any, Protocol

import numpy as np


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[np.ndarray]: ...


class FastEmbedEmbedder:
    """Local bge-small via fastembed. Model loads lazily on first embed."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        self._model_name = model_name
        self._model: Any = None

    def embed(self, texts: list[str]) -> list[np.ndarray]:
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(self._model_name)
        return [np.asarray(v, dtype=np.float32) for v in self._model.embed(texts)]
