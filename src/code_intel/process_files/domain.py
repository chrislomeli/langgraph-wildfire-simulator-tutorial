from __future__ import annotations

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
