from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from typing import ClassVar

from langchain_text_splitters import RecursiveCharacterTextSplitter

from code_intel.process_files.domain import (
    Chunk,
    ChunkConfig,
    FileMeta,
    FileType,
    SymbolInfo,
)


@dataclass
class Splitter(ABC):
    meta: FileMeta
    config: ChunkConfig

    extensions: ClassVar[tuple[str, ...]] = ()
    file_type: ClassVar[FileType] = FileType.TEXT
    is_default: ClassVar[bool] = False

    @abstractmethod
    def split(self, text_stream: Iterator[str]) -> Iterator[Chunk]: ...

    def make_chunk(
        self,
        start_line: int,
        end_line: int,
        text: str,
        symbol: SymbolInfo | None = None,
    ) -> Chunk:
        return Chunk(
            splitter_name=type(self).__name__,
            meta=self.meta,
            start_line=start_line,
            end_line=end_line,
            text=text,
            symbol=symbol,
        )

    def emit(
        self,
        start_line: int,
        end_line: int,
        text: str,
        symbol: SymbolInfo | None = None,
    ) -> Iterator[Chunk]:
        """Yield one chunk, or several if `text` exceeds config.max_chunk_chars.

        Structural splitters call this instead of make_chunk so an oversized
        symbol/section is transparently sub-split. The symbol is carried onto
        every sub-chunk; line numbers are interpolated from newline counts and
        are approximate for sub-chunks past the first.
        """
        max_chars = self.config.max_chunk_chars
        if len(text) <= max_chars:
            yield self.make_chunk(start_line, end_line, text, symbol=symbol)
            return

        lc = RecursiveCharacterTextSplitter(
            chunk_size=max_chars,
            chunk_overlap=self.config.overlap,
        )
        scan_pos = 0
        for piece in lc.split_text(text):
            idx = text.find(piece, max(0, scan_pos))
            if idx == -1:
                idx = scan_pos
            s = start_line + text[:idx].count("\n")
            e = s + piece.count("\n")
            scan_pos = max(idx + 1, idx + len(piece) - self.config.overlap)
            yield self.make_chunk(s, e, piece, symbol=symbol)

