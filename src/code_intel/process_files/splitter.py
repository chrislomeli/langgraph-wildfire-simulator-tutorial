from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from typing import ClassVar

from code_intel.process_files.domain import (
    Chunk,
    ChunkConfig,
    FileMeta,
    FileType,
    Kind,
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

    def make_chunk(self, start_line: int, end_line: int, text: str) -> Chunk:
        return Chunk(
            splitter_name=type(self).__name__,
            meta=self.meta,
            start_line=start_line,
            end_line=end_line,
            text=text,
        )


class FixedSplitter(Splitter):
    """Character-window splitter with overlap. Naive baseline; line numbers
    under overlap are approximate."""

    extensions = (".json", ".yaml", ".yml", ".toml", ".j2", ".txt")
    file_type = FileType.TEXT
    is_default = True

    def split(self, text_stream: Iterator[str]) -> Iterator[Chunk]:
        chunk_size = self.config.chunk_size
        overlap = self.config.overlap
        buffer = ""
        buffer_start_line = 1
        current_line = 0

        for line in text_stream:
            current_line += 1
            buffer += line
            while len(buffer) >= chunk_size:
                head = buffer[:chunk_size]
                lines_consumed = head[: chunk_size - overlap].count("\n")
                lines_in_head = head.count("\n")
                end_line = buffer_start_line + max(lines_in_head - 1, 0)
                yield self.make_chunk(buffer_start_line, end_line, head)
                buffer = buffer[chunk_size - overlap:]
                buffer_start_line += lines_consumed

        if buffer:
            end_line = max(current_line, buffer_start_line)
            yield self.make_chunk(buffer_start_line, end_line, buffer)


class SplitterRegistry:
    """Maps file extensions to Splitter classes; builds a fresh splitter per file."""

    def __init__(self, root: Path, default_config: ChunkConfig = ChunkConfig()):
        self._root = root
        self._default_config = default_config
        self._by_ext: dict[str, type[Splitter]] = {}
        self._default: type[Splitter] | None = None

    def add(self, cls: type[Splitter]) -> SplitterRegistry:
        for ext in cls.extensions:
            self._by_ext[ext] = cls
        if cls.is_default:
            self._default = cls
        return self

    def for_path(self, path: Path, kind: Kind) -> Splitter | None:
        cls = self._by_ext.get(path.suffix, self._default)
        if cls is None:
            return None
        stat = path.stat()
        meta = FileMeta(
            project_folder=str(path.parent.relative_to(self._root)),
            file_name=path.name,
            file_type=cls.file_type,
            kind=kind,
            last_modified=stat.st_mtime,
        )
        config = self._default_config
        if stat.st_size < config.chunk_size:
            config = replace(config, overlap=0)
        return cls(meta=meta, config=config)
