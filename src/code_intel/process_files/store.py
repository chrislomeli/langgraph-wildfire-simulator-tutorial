from __future__ import annotations

import logging
from collections.abc import Iterable

from code_intel.process_files.embedder import Embedder
from code_intel.process_files.domain import Chunk

log = logging.getLogger(__name__)


class VectorStore:
    """Buffers chunks across files and embeds them in batches at flush time.

    The persist step is a stub — replace `_persist` when wiring pgvector.
    """

    def __init__(self, embedder: Embedder, batch_size: int = 64):
        self._embedder = embedder
        self._batch_size = batch_size
        self._buffer: list[Chunk] = []

    def store_chunk(self, chunk: Chunk) -> None:
        self._buffer.append(chunk)
        if len(self._buffer) >= self._batch_size:
            self.flush()

    def flush(self) -> None:
        if not self._buffer:
            return
        texts = [c.text for c in self._buffer]
        vectors = self._embedder.embed_batch(texts)
        for chunk, vec in zip(self._buffer, vectors, strict=True):
            chunk.vector = vec
        self._persist(self._buffer)
        self._buffer = []

    def _persist(self, chunks: Iterable[Chunk]) -> None:
        for c in chunks:
            log.info(
                "persist %s:%s/%s %d-%d (%d chars)",
                c.meta.kind,
                c.meta.project_folder,
                c.meta.file_name,
                c.start_line,
                c.end_line,
                len(c.text),
            )
