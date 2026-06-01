from __future__ import annotations

import datetime
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import numpy as np


def find_root(marker: str = "pyproject.toml") -> Path:
    current = Path(__file__).parent
    while current != current.parent:
        if (current / marker).exists():
            return current
        current = current.parent
    raise FileNotFoundError(f"Could not find {marker}")


ROOT_PATH = find_root()


class FileType(StrEnum):
    PYTHON = "python"
    MARKDOWN = "markdown"
    JSON = "json"
    YAML = "yaml"
    TOML = "toml"
    TEMPLATE = "template"
    TEXT = "text"


class Kind(StrEnum):
    SOURCE = "source"
    TEST = "test"
    DOC = "doc"
    CONFIG = "config"
    TEMPLATE = "template"


class SymbolKind(StrEnum):
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    MODULE = "module"
    IMPORTS = "imports"
    HEADING_SECTION = "heading_section"


@dataclass(frozen=True)
class ChunkConfig:
    chunk_size: int = 1000
    overlap: int = 200
    # Hard ceiling on a single chunk's text length. Structural splitters
    # (Python, Markdown) emit one chunk per symbol/section, which can far
    # exceed chunk_size for large functions or doc sections. Chunks over this
    # are sub-split before embedding — both to avoid the embedder's token-limit
    # truncation and to stop one oversized chunk from padding an entire batch.
    max_chunk_chars: int = 4000


@dataclass(frozen=True)
class FileMeta:
    project_folder: str
    file_name: str
    file_type: FileType
    kind: Kind
    last_modified: float


@dataclass(frozen=True)
class SymbolInfo:
    name: str
    kind: SymbolKind
    parent: str | None = None
    heading_path: tuple[str, ...] | None = None


@dataclass
class Chunk:
    splitter_name: str
    meta: FileMeta
    start_line: int
    end_line: int
    text: str
    vector: np.ndarray | None = None
    symbol: SymbolInfo | None = None

    def to_db_row(self) -> tuple:
        """Return tuple for INSERT/UPDATE — computed fields excluded."""
        if self.symbol:
            symbol_name = self.symbol.name
            symbol_kind = self.symbol.kind
            symbol_parent = self.symbol.parent
            symbol_heading_path = self.symbol.heading_path
        else:
            symbol_name = symbol_kind = symbol_parent = symbol_heading_path = None

        return (
            self.splitter_name,
            self.start_line,
            self.end_line,
            self.text,
            self.vector,
            self.meta.project_folder,
            self.meta.file_name,
            self.meta.file_type,
            self.meta.kind,
            symbol_name,
            symbol_kind,
            symbol_parent,
            list(symbol_heading_path) if symbol_heading_path else None,
            datetime.datetime.fromtimestamp(self.meta.last_modified, tz=datetime.timezone.utc),
        )

    def embed_text(self) -> str:
        if self.symbol and self.symbol.heading_path:
            prefix = " > ".join(self.symbol.heading_path)
            return f"{prefix}\n\n{self.text}"
        if self.symbol and self.symbol.kind != SymbolKind.MODULE:
            prefix = f"{self.meta.file_name} {self.symbol.kind} {self.symbol.name}"
            return f"{prefix}\n\n{self.text}"
        return self.text