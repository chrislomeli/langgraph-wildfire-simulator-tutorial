from __future__ import annotations

import logging
from collections.abc import Iterable

from code_intel.process_files.embedder import Embedder
from code_intel.process_files.domain import Chunk
from stores.postgres import PgGateway, get_pg_gateway
from stores.postgres.code_intel_repo import CodeIntelRepo

log = logging.getLogger(__name__)


class VectorStore:
    """Buffers chunks across files and embeds them in batches at flush time.
    """

    def __init__(self, embedder: Embedder, pg_gateway, batch_size: int = 32):
        self._embedder = embedder
        self._batch_size = batch_size
        self._buffer: list[Chunk] = []
        self._pg = pg_gateway
        self._db = CodeIntelRepo(pg_gateway=pg_gateway, truncate=True)

    def __enter__(self) -> "VectorStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            self.flush()
        finally:
            self._pg.close()

    def close(self) -> None:
        self.flush()
        self._pg.close()

    def store_chunk(self, chunk: Chunk) -> None:
        self._buffer.append(chunk)
        if len(self._buffer) >= self._batch_size:
            self.flush()

    def flush(self) -> None:
        if not self._buffer:
            return
        # Length-sort so each embed sub-batch groups similarly-sized texts.
        # fastembed/ONNX pads every sequence in a batch up to the longest one,
        # so mixing one long chunk with many short ones makes the whole batch
        # pay the long chunk's cost. Bucketing keeps padding waste local.
        self._buffer.sort(key=lambda c: len(c.embed_text()))
        print("....flush.....", end="", flush=True)
        for i in range(0, len(self._buffer), self._batch_size):
            batch = self._buffer[i : i + self._batch_size]
            texts = [c.embed_text() for c in batch]
            log.info(
                "embedding %d chunks (max %d chars, total %d chars)",
                len(texts),
                max(len(t) for t in texts),
                sum(len(t) for t in texts),
            )
            vectors = self._embedder.embed_batch(texts)
            for chunk, vec in zip(batch, vectors, strict=True):
                chunk.vector = vec
        self._persist(self._buffer)
        self._buffer = []

    def _persist(self, chunks: Iterable[Chunk]) -> None:
        self._db.save_chunks(list(chunks))
