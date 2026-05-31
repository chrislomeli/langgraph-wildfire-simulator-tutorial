"""Local text embedding via fastembed.

Wraps fastembed.TextEmbedding to produce numpy arrays compatible with the
pgvector schema. fastembed uses ONNX Runtime — no PyTorch or GPU required.
The model is downloaded once on first use and cached automatically.
"""

from __future__ import annotations

import numpy as np
from fastembed import TextEmbedding

# Must match code_intel.chunks.vector dimension in the DDL (768).
_MODEL = "jinaai/jina-embeddings-v2-base-code"


class Embedder:
    def __init__(self, model: str = _MODEL):
        self._model = TextEmbedding(model_name=model)

    def embed(self, text: str) -> np.ndarray:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        return [np.array(v, dtype=np.float32) for v in self._model.embed(texts)]
