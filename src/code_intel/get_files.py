"""- `src/**/*.py` — source code
- `tests/**/*.py` — tests (often the best "how is X used" examples)
- `docs/**/*.md` — design docs, rubrics, this file
- `src/prompts/templates/**/*.j2` — prompt templates (substantive content)
- `*.toml`, manifest YAMLs — small, occasionally queried
"""
import dataclasses
import os
from pathlib import Path
from abc import ABC, abstractmethod
from typing import Iterator

CHUNK_DIVIDER = "\n^|^\n"


"""
# Good RAG chunk structure regardless of parser
{
    "text": "def process_order(order_id: str) -> dict:\n    ...",
    "metadata": {
        "type": "function",
        "name": "process_order",
        "name": "process_order",
        "file": "orders/service.py",
        "lines": (42, 67),
        "parent_class": "OrderService",   # nested? track it
        "language": "python"
    }
}
One gotcha w
"""



class Splitter(ABC):
    @abstractmethod
    def split(self, text_stream: Iterator[str]) -> Iterator[dict]:
        """Consume a stream of text, yield chunk dicts."""
        ...
    @abstractmethod
    def format(self, text_stream: Iterator[str]) -> Iterator[dict]:
        """Consume a stream of text, yield chunk dicts."""
        ...


class MarkdownSplitter(Splitter):
    def split(self, text_stream):
        # truly streaming — never buffers whole file
        ...


class TreeSitterSplitter(Splitter):
    def split(self, text_stream):
        # honest: buffers full file, then parses
        full_text = "".join(text_stream)
        # ... parse and yield chunks
        ...


# stream_chunks() body moves into here
@dataclasses.dataclass
class FixedSplitter(Splitter):
    chunk_size: int = 1000
    overlap: int = 200

    def split(self, text_stream: Iterator[str]) -> Iterator[dict]:
        buffer = ""
        for line in text_stream:
            buffer += line
            while len(buffer) >= self.chunk_size:
                yield buffer[:self.chunk_size] + CHUNK_DIVIDER
                buffer = buffer[self.chunk_size - self.overlap:]
        if buffer:
            yield buffer


SPLITTERS = {
    ".py": FixedSplitter(),
    ".sh": FixedSplitter(),
    ".md": FixedSplitter(),
    "*": FixedSplitter(),  # fallback
}


def get_splitter(filepath: str) -> Splitter:
    ext = Path(filepath).suffix
    return SPLITTERS.get(ext, SPLITTERS["*"])


# -----------------------------------------------------
def stream_file(path: Path):
    if path.is_file():
        with path.open('r') as f:
            for line in f:
                yield line


def handle_files(text_files: list[Path]):
    for path in text_files:
        reader = stream_file(path)
        if split_handler := get_splitter(path.name):
            splitter = split_handler.split(reader)
            for chunk in splitter:
                print(f"---CHUNK {os.path.basename(path)}---")
                print(chunk)








# Define the directory to search and your patterns
patterns = ['*.py', '*.md', '*.json']
exclude = {"node_modules", ".git", "__pycache__", ".venv", ".idea"}
root_dir = Path("/Users/chrislomeli/Source/PROJECTS/agenticAI/wildfire/wildfire-simulator-step_09")


def walk_files(base_folder: Path, pattern: str):
    return [p for p in base_folder.rglob(pattern) if not any(part in exclude for part in p.parts)]


if __name__ == '__main__':
    files = {
        "src_python_files": walk_files(root_dir / "src", "*.py"),
        "test_python_files": walk_files(root_dir / "tests", "*.py"),
        "docs": walk_files(root_dir / "docs", "*.md"),
        "prompts": walk_files(root_dir / "src" / "prompts", "*.j2"),
        "json": walk_files(root_dir, "*.json"),
        "yaml": walk_files(root_dir, "*.*ml")
    }
    for _, group in files.items():
        handle_files(group)
