from __future__ import annotations

import re
from collections.abc import Iterator

from langchain_text_splitters import MarkdownHeaderTextSplitter

from code_intel.process_files.domain import Chunk, FileType, SymbolInfo, SymbolKind
from code_intel.process_files.splitters.base import Splitter

_HEADERS_TO_SPLIT_ON = [
    ("#", "h1"),
    ("##", "h2"),
    ("###", "h3"),
    ("####", "h4"),
]

_HEADING_RE = re.compile(r"^#{1,6}\s+(.*)")


class MarkdownSplitter(Splitter):
    """Heading-hierarchy splitter using LangChain's MarkdownHeaderTextSplitter.

    Each chunk corresponds to one heading section. Every chunk carries the full
    breadcrumb path from the document root down to its own heading in
    SymbolInfo.heading_path. Line numbers are approximate (based on heading
    position; end_line estimated from content length).
    """

    extensions = (".md",)
    file_type = FileType.MARKDOWN
    is_default = False

    def split(self, text_stream: Iterator[str]) -> Iterator[Chunk]:
        lines = list(text_stream)
        content = "".join(lines)

        # Build heading-text → first line_number map for approximate tracking.
        # setdefault keeps the first occurrence when headings repeat.
        heading_line: dict[str, int] = {}
        for i, line in enumerate(lines, 1):
            m = _HEADING_RE.match(line.rstrip())
            if m:
                heading_line.setdefault(m.group(1).strip(), i)

        lc = MarkdownHeaderTextSplitter(
            headers_to_split_on=_HEADERS_TO_SPLIT_ON,
            strip_headers=False,
        )

        for doc in lc.split_text(content):
            text = doc.page_content.strip()
            if not text:
                continue

            meta_values = list(doc.metadata.values())

            if not meta_values:
                # Content before the first heading — yield as an unstructured chunk.
                yield from self.emit(1, text.count("\n") + 1, text)
                continue

            heading_path = tuple(meta_values)
            leaf = meta_values[-1]
            parent = meta_values[-2] if len(meta_values) >= 2 else None

            start_line = heading_line.get(leaf, 1)
            end_line = start_line + text.count("\n")

            symbol = SymbolInfo(
                name=leaf,
                kind=SymbolKind.HEADING_SECTION,
                parent=parent,
                heading_path=heading_path,
            )
            yield from self.emit(start_line, end_line, text, symbol=symbol)
