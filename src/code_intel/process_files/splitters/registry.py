from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from code_intel.process_files.domain import (
    ChunkConfig,
    FileMeta,
    Kind,
)
from code_intel.process_files.splitters.base import Splitter


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
