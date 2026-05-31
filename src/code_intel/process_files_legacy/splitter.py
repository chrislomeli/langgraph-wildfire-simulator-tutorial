import dataclasses
from abc import ABC, abstractmethod
from collections.abc import Iterator
from enum import StrEnum
from pathlib import Path
from typing import Any

from code_intel.process_files.embedder import Embedder

CHUNK_DIVIDER = "\n^|^\n"


def find_root(marker: str = "pyproject.toml") -> Path:
    current = Path(__file__).parent
    while current != current.parent:  # stop at filesystem root
        if (current / marker).exists():
            return current
        current = current.parent
    raise FileNotFoundError(f"Could not find {marker}")


ROOT_PATH = find_root()


class FileType(StrEnum):
    PYTHON = "python"
    MARKDOWN = "markdown"
    JSON = "json"
    SHELL = "sh"
    YAML = "yaml"
    TEXT = "txt"


@dataclasses.dataclass
class Chunk:
    splitter_name: str
    project_folder: str
    file_name: str
    file_type: str
    start_line: int
    end_line: int
    text_size: int
    text: str
    vector: Any


class Splitter(ABC):
    embedder: Embedder = Embedder()
    chunk_size: int = 1000
    overlap: int = 200
    file_type: str | None = None
    file_name: str | None = None
    project_folder: str | None = None

    @abstractmethod
    def split(self, text_stream: Iterator[str]) -> Iterator[Chunk]: ...

    def init(self, project_folder: str, file_name: str, file_type: str):
        self.file_name = file_name
        self.file_type = file_type
        self.project_folder = project_folder

    def make_chunk(self, start_line: int, end_line: int, text: str):
        vect = self.embedder.embed(text)
        return Chunk(
            splitter_name=self.__class__.__name__,
            project_folder=self.project_folder,
            file_name=self.file_name,
            file_type=str(self.file_type),
            start_line=start_line,
            end_line=end_line,
            text_size=len(text),
            text=text,
            vector=vect,
        )


@dataclasses.dataclass
class SplitterType:
    type: FileType
    splitter: Splitter


# stream_chunks() body moves into here
@dataclasses.dataclass
class FixedSplitter(Splitter):

    def split(self, text_stream: Iterator[str]) -> Iterator[Chunk]:
        buffer = ""
        start_line = 1
        end_line = 0

        for line in text_stream:
            end_line += 1
            buffer += line

            while len(buffer) >= self.chunk_size:
                ch = self.make_chunk(
                    start_line=start_line,
                    end_line=end_line,
                    text=buffer[: self.chunk_size] + CHUNK_DIVIDER,
                )
                yield ch

                buffer = buffer[self.chunk_size - self.overlap :]
                start_line = end_line + 1

        if buffer:
            ch = self.make_chunk(start_line=start_line, end_line=end_line, text=buffer)
            yield ch


SPLITTERS = {
    ".py": SplitterType(type=FileType.PYTHON, splitter=FixedSplitter()),
    ".md": SplitterType(type=FileType.MARKDOWN, splitter=FixedSplitter()),
    ".j2": SplitterType(type=FileType.MARKDOWN, splitter=FixedSplitter()),
    ".json": SplitterType(type=FileType.MARKDOWN, splitter=FixedSplitter()),
    ".toml": SplitterType(type=FileType.MARKDOWN, splitter=FixedSplitter()),
    ".yaml": SplitterType(type=FileType.MARKDOWN, splitter=FixedSplitter()),
    ".yml": SplitterType(type=FileType.MARKDOWN, splitter=FixedSplitter()),
    "*": SplitterType(type=FileType.TEXT, splitter=FixedSplitter()),
}


def get_splitter(path: Path) -> Splitter | None:
    file_name = path.name
    file_size_bytes = path.stat().st_size
    ext = Path(file_name).suffix
    splitter_type = SPLITTERS.get(ext, None)
    if splitter_type:
        splitter = splitter_type.splitter
        file_type = str(splitter_type.type)
        project_folder = str(path.parent.relative_to(ROOT_PATH))
        splitter.init(project_folder=project_folder, file_name=path.name, file_type=file_type)
        if splitter.chunk_size > file_size_bytes:
            splitter.overlap = 0
        return splitter
    print(f"Skipping {file_name}")
    return None
