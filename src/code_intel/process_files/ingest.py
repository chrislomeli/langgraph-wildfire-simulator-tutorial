from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from code_intel.process_files.embedder import Embedder
from code_intel.process_files.splitter import FixedSplitter, SplitterRegistry
from code_intel.process_files.store import VectorStore
from code_intel.process_files.domain import ROOT_PATH, Kind

log = logging.getLogger(__name__)

EXCLUDE: frozenset[str] = frozenset(
    {"node_modules", ".git", "__pycache__", ".venv", ".idea", "scripts"}
)


def stream_file(path: Path) -> Iterator[str]:
    with path.open("r", encoding="utf-8") as f:
        yield from f


@dataclass
class CorpusWalker:
    root: Path
    exclude: frozenset[str] = EXCLUDE

    GROUPS: ClassVar[tuple[tuple[str, str, Kind], ...]] = (
        ("src", "*.py", Kind.SOURCE),
        ("tests", "*.py", Kind.TEST),
        ("docs", "*.md", Kind.DOC),
        ("src/prompts", "*.j2", Kind.TEMPLATE),
        (".", "*.toml", Kind.CONFIG),
        (".", "*.yaml", Kind.CONFIG),
        (".", "*.yml", Kind.CONFIG),
        (".", "*.json", Kind.CONFIG),
    )

    def walk(self) -> Iterator[tuple[Path, Kind]]:
        seen: set[Path] = set()
        for subdir, pattern, kind in self.GROUPS:
            base = self.root / subdir
            if not base.exists():
                continue
            for p in base.rglob(pattern):
                if not p.is_file():
                    continue
                if any(part in self.exclude for part in p.parts):
                    continue
                if p in seen:
                    continue
                seen.add(p)
                yield p, kind


@dataclass
class Ingestor:
    walker: CorpusWalker
    registry: SplitterRegistry
    store: VectorStore

    def run(self) -> None:
        try:
            for path, kind in self.walker.walk():
                self._handle(path, kind)
        finally:
            self.store.flush()

    def _handle(self, path: Path, kind: Kind) -> None:
        splitter = self.registry.for_path(path, kind)
        if splitter is None:
            return
        try:
            for chunk in splitter.split(stream_file(path)):
                self.store.store_chunk(chunk)
        except UnicodeDecodeError:
            log.warning("skipping non-utf8 file: %s", path)
        except OSError as e:
            log.warning("read error on %s: %s", path, e)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    embedder = Embedder()
    registry = SplitterRegistry(root=ROOT_PATH).add(FixedSplitter)
    store = VectorStore(embedder=embedder)
    walker = CorpusWalker(root=ROOT_PATH)
    Ingestor(walker=walker, registry=registry, store=store).run()


if __name__ == "__main__":
    main()
