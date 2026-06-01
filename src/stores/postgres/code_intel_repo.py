"""Code intelligence repository — bulk insert and retrieve corpus chunks."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from code_intel.process_files.domain import Chunk
from stores.postgres.gateway import PgGateway

logger = logging.getLogger(__name__)


class CodeIntelRepo:
    """Repository for persisting and retrieving code intelligence chunks."""

    def __init__(self, pg_gateway: PgGateway, truncate: bool = False):
        self._pg = pg_gateway
        if truncate:
            self.truncate_pinned_corpus()

    def truncate_pinned_corpus(self) -> None:
        with self._pg.conn() as conn, conn.cursor() as cur:
            cur.execute("truncate code_intel.chunks restart identity")

    def save_chunks(self, chunks: list[Chunk]) -> int:
        """Bulk insert chunks. Returns number of rows inserted."""
        if not chunks:
            return 0

        rows = [r.to_db_row() for r in chunks]

        with self._pg.conn() as conn, conn.cursor() as cur:
            cur.executemany(
                """
                insert into code_intel.chunks (splitter_name,
                                               start_line,
                                               end_line,
                                               text,
                                               vector,
                                               project_folder,
                                               file_name,
                                               file_type,
                                               kind,
                                               symbol_name,
                                               symbol_kind,
                                               parent_symbol,
                                               heading_path,
                                               last_modified)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                rows,
            )
            return len(chunks)

    def search_chunks(
        self,
        vector: np.ndarray,
        k: int = 10,
        kind: str | None = None,
        folder_prefix: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return the top-k chunks by cosine similarity to vector.

        Optionally scoped by kind ('source', 'test', 'doc', etc.) and/or a
        project_folder prefix (e.g. 'src/code_intel').

        Returns dicts with the same keys as the SELECT below plus 'score'
        (cosine similarity, 0–1, higher = more similar).
        """
        conditions = ["1=1"]
        params: list[Any] = []

        if kind is not None:
            conditions.append("kind = %s")
            params.append(kind)
        if folder_prefix is not None:
            conditions.append("project_folder LIKE %s")
            params.append(f"{folder_prefix}%")

        where = " AND ".join(conditions)

        # vector <=> is cosine *distance* (0 = identical, 2 = opposite).
        # 1 - distance converts to similarity so callers get an intuitive score.
        sql = f"""
            SELECT chunk_id,
                   project_folder,
                   file_name,
                   kind,
                   start_line,
                   end_line,
                   text,
                   symbol_name,
                   symbol_kind,
                   parent_symbol,
                   1 - (vector <=> %s::vector) AS score
            FROM   code_intel.chunks
            WHERE  {where}
            ORDER  BY vector <=> %s::vector
            LIMIT  %s
        """
        # vector appears twice: once in SELECT for score, once in ORDER BY.
        vec_list = vector.tolist()
        params = [vec_list] + params + [vec_list, k]

        with self._pg.conn() as conn, conn.cursor(row_factory=__import__('psycopg').rows.dict_row) as cur:
            cur.execute(sql, params)
            return cur.fetchall()
