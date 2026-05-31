from pathlib import Path

from code_intel.process_files.splitter import ROOT_PATH, get_splitter
from code_intel.process_files.store import VectorStore

# -----------------------------------------------------


store = VectorStore()


def stream_file(path: Path):
    if path.is_file():
        with path.open("r") as f:
            yield from f


def handle_file(path: Path):
    reader = stream_file(path)
    if split_handler := get_splitter(path):
        for chunk in split_handler.split(reader):
            store.store_chunk(chunk)


# Define the directory to search and your patterns
exclude = {"node_modules", ".git", "__pycache__", ".venv", ".idea", "scripts"}


def walk_files(base_folder: Path, pattern: str):
    return [p for p in base_folder.rglob(pattern) if not any(part in exclude for part in p.parts)]


if __name__ == "__main__":
    root_dir = ROOT_PATH
    files = {
        "src_python_files": walk_files(root_dir / "src", "*.py"),
        "test_python_files": walk_files(root_dir / "tests", "*.py"),
        "docs": walk_files(root_dir / "docs", "*.md"),
        "prompts": walk_files(root_dir / "src" / "prompts", "*.j2"),
        "json": walk_files(root_dir, "*.json"),
        "yaml": walk_files(root_dir, "*.*ml"),
    }
    for _, group in files.items():
        for path in group:
            handle_file(path)
