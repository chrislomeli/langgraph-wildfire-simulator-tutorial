from __future__ import annotations

from collections.abc import Iterator

from langchain_text_splitters import RecursiveCharacterTextSplitter

from code_intel.process_files.domain import Chunk, FileType
from code_intel.process_files.splitters.base import Splitter


class FixedSplitter(Splitter):
    """Naive fixed-size baseline using LangChain's RecursiveCharacterTextSplitter.

    Splits on structural separators (paragraphs → newlines → spaces → chars)
    before falling back to hard character cuts. Line numbers are approximate
    for chunks that span overlap regions.
    """

    extensions = (".json", ".yaml", ".yml", ".toml", ".j2", ".txt")
    file_type = FileType.TEXT
    is_default = True

    def split(self, text_stream: Iterator[str]) -> Iterator[Chunk]:
        content = "".join(text_stream)
        lc = RecursiveCharacterTextSplitter(
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.overlap,
        )
        scan_pos = 0
        for chunk_text in lc.split_text(content):
            idx = content.find(chunk_text, max(0, scan_pos))
            if idx == -1:
                idx = scan_pos
            start_line = content[:idx].count("\n") + 1
            end_line = start_line + chunk_text.count("\n")
            scan_pos = max(idx + 1, idx + len(chunk_text) - self.config.overlap)
            yield self.make_chunk(start_line, end_line, chunk_text)
