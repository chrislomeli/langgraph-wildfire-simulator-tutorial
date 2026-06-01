from __future__ import annotations

# tree-sitter is a *parser* library: it turns source text into a Concrete Syntax
# Tree (CST).  Unlike an AST, a CST keeps every token including whitespace and
# comments, so we can recover exact byte/line positions for every construct.
#
# The two packages we need:
#   tree-sitter          — the core parser engine (Language, Parser, Node)
#   tree-sitter-python   — a compiled grammar for Python; tspython.language()
#                          returns a raw capsule that Language() wraps.

from collections.abc import Iterator
from typing import ClassVar

import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

from code_intel.process_files.domain import Chunk, FileType, SymbolInfo, SymbolKind
from code_intel.process_files.splitters.base import Splitter

# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

# Language is a thin wrapper around the grammar binary.  One instance per
# grammar is fine; it is stateless.
_LANGUAGE = Language(tspython.language())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node_text(node: Node, source: bytes) -> str:
    # node.start_byte / end_byte are byte offsets into the original source.
    # Slicing source and decoding gives us the exact text tree-sitter saw.
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _start_line(node: Node) -> int:
    # tree-sitter uses 0-indexed rows; we store 1-indexed line numbers.
    return node.start_point.row + 1


def _end_line(node: Node) -> int:
    return node.end_point.row + 1


def _symbol_name(node: Node) -> str | None:
    # Most definition nodes expose a 'name' field — the identifier token.
    # e.g. for `def foo():` → child_by_field_name("name") → Node("identifier", "foo")
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    return name_node.text.decode("utf-8", errors="replace")


def _unwrap_decorated(node: Node) -> Node:
    # A decorated_definition wraps the real definition (function or class)
    # inside a 'definition' field:
    #
    #   decorated_definition
    #     decorator  → @staticmethod
    #     definition → function_definition
    #                      name → baz
    #
    # We return the inner node so callers can treat it like a bare definition.
    # If the field is missing (shouldn't happen) we fall back to the outer node.
    inner = node.child_by_field_name("definition")
    return inner if inner is not None else node


# ---------------------------------------------------------------------------
# Preamble collector
# ---------------------------------------------------------------------------

# The "preamble" is everything at the top of the module before the first
# function or class: the module docstring, imports, and module-level constants.
# We group all of it into one MODULE chunk so the embedder sees it as a unit.
_PREAMBLE_TYPES = frozenset(
    {
        "future_import_statement", # from __future__ import annotations
        "import_statement",        # import os
        "import_from_statement",   # from pathlib import Path
        "expression_statement",    # module docstring or bare string literal
        "assignment",              # MODULE_CONSTANT = 42
        "augmented_assignment",    # X += 1  (rare at module level but valid)
        "comment",                 # # top-of-file comments
    }
)


def _collect_preamble_text(
    children: list[Node], source: bytes
) -> tuple[str, int, int] | None:
    """
    Walk the top-level children and gather consecutive preamble nodes into a
    single text blob.  Returns (text, start_line, end_line) or None if there
    are no preamble nodes at all.

    We stop as soon as we hit a function_definition, class_definition, or
    decorated_definition — those get their own chunks.
    """
    preamble_nodes: list[Node] = []
    for child in children:
        if child.type in _PREAMBLE_TYPES:
            preamble_nodes.append(child)
        else:
            # First non-preamble node — stop collecting.
            break

    if not preamble_nodes:
        return None

    # Stitch all preamble nodes back together preserving their exact source.
    text = "\n".join(_node_text(n, source) for n in preamble_nodes)
    return text, _start_line(preamble_nodes[0]), _end_line(preamble_nodes[-1])


# ---------------------------------------------------------------------------
# Class body splitter
# ---------------------------------------------------------------------------

# When we encounter a class_definition we produce TWO kinds of chunks:
#
#   1. CLASS chunk  — the class header + any class-level code (docstring,
#                     class variables) up to the first method.
#   2. METHOD chunk — one per function_definition inside the class body.
#
# This mirrors how humans think about code: "the Foo class" vs "Foo.bar()".

def _split_class(
    node: Node,  # the class_definition (or decorated_definition) node
    source: bytes,
    class_name: str,
    emit,  # bound Splitter.emit — size-caps oversized chunks
) -> Iterator[Chunk]:
    """
    Yield a CLASS header chunk followed by one METHOD chunk per method.

    The CLASS chunk spans from the `class` keyword to the line just before
    the first method (or to the end of the class if there are no methods).
    """
    # Find the body block_node — the indented suite after the colon.
    # tree-sitter names it 'body' on class_definition.
    body = node.child_by_field_name("body")
    if body is None:
        # Degenerate: class with no body (parse error or stub).  Emit as-is.
        symbol = SymbolInfo(name=class_name, kind=SymbolKind.CLASS)
        yield from emit(_start_line(node), _end_line(node), _node_text(node, source), symbol=symbol)
        return

    # Separate body children into "header material" (docstring, class vars)
    # and method definitions.
    header_nodes: list[Node] = []
    method_nodes: list[Node] = []

    for child in body.named_children:
        # decorated_definition wraps a function_definition with decorators.
        effective = _unwrap_decorated(child) if child.type == "decorated_definition" else child
        if effective.type == "function_definition":
            method_nodes.append(child)  # keep the outer decorated node for text
        else:
            if not method_nodes:
                # Still in the header section; collect it.
                header_nodes.append(child)
            # After first method we ignore class-level code between methods
            # (rare — e.g. class-level if blocks).  Keeps chunks clean.

    # --- CLASS header chunk ---
    # Includes the `class Foo(Base):` line plus docstring / class variables.
    if header_nodes:
        # Span from the class keyword to the last header node.
        class_end = _end_line(header_nodes[-1])
    else:
        # No header nodes: header is just the `class Foo:` line itself.
        # node.start_point is the `class` keyword row.
        class_end = _start_line(node)  # single-line header

    # Reconstruct header text: class signature line + header body nodes.
    # We slice the source bytes directly so we don't have to reassemble tokens.
    header_end_byte = header_nodes[-1].end_byte if header_nodes else node.start_byte + source[node.start_byte:].find(b":") + 1
    header_text = source[node.start_byte : (header_nodes[-1].end_byte if header_nodes else body.start_byte)].decode("utf-8", errors="replace").rstrip()

    class_symbol = SymbolInfo(name=class_name, kind=SymbolKind.CLASS)
    yield from emit(_start_line(node), class_end, header_text, symbol=class_symbol)

    # --- METHOD chunks ---
    for method_node in method_nodes:
        # Peel off decorator wrapper to get the actual function_definition.
        fn_node = _unwrap_decorated(method_node) if method_node.type == "decorated_definition" else method_node
        method_name = _symbol_name(fn_node) or "<anonymous>"

        # The chunk text includes the decorator lines (if any) because that
        # context matters for embeddings (@property, @staticmethod, etc.).
        text = _node_text(method_node, source)

        symbol = SymbolInfo(
            name=method_name,
            kind=SymbolKind.METHOD,
            parent=class_name,  # <-- "this method lives inside class_name"
        )
        yield from emit(_start_line(method_node), _end_line(method_node), text, symbol=symbol)


# ---------------------------------------------------------------------------
# Main splitter
# ---------------------------------------------------------------------------


class TreeSitterPythonSplitter(Splitter):
    """
    Structural Python splitter backed by tree-sitter.

    Unlike FixedSplitter (which blindly cuts every N characters), this splitter
    understands Python syntax.  Each chunk corresponds to a *meaningful unit*:

        - MODULE   — the file preamble (imports, module docstring, constants)
        - FUNCTION — a top-level function or async function
        - CLASS    — a class header + class variables / docstring
        - METHOD   — a method inside a class (knows its parent class name)

    Line numbers are exact (from the CST), not approximate.

    ClassVar contract (inherited from Splitter):
        extensions  — file suffixes this splitter handles
        file_type   — the FileType enum value written to the DB
        is_default  — False: only used when the registry maps .py to this class
    """

    extensions: ClassVar[tuple[str, ...]] = (".py",)
    file_type: ClassVar[FileType] = FileType.PYTHON
    is_default: ClassVar[bool] = False

    # --- Lazy-loaded shared parser ---
    #
    # Parser.parse() is thread-safe; Parser itself is not.  One Parser per
    # splitter instance would be wasteful (each file gets a fresh Splitter from
    # the registry).  We keep a single class-level instance; if you ever need
    # true thread safety, swap this for a threading.local().
    _parser: ClassVar[Parser | None] = None

    @classmethod
    def _get_parser(cls) -> Parser:
        # Lazy init: build once, reuse forever.
        if cls._parser is None:
            cls._parser = Parser(_LANGUAGE)
        return cls._parser

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def split(self, text_stream: Iterator[str]) -> Iterator[Chunk]:
        """
        Parse the file and yield one Chunk per top-level symbol.

        Flow:
            1. Materialise the stream → bytes  (tree-sitter works on bytes)
            2. Parse → CST
            3. Walk the module's named_children
            4. Collect preamble nodes → MODULE chunk
            5. For each function_definition → FUNCTION chunk
            6. For each class_definition   → CLASS + METHOD chunks
            7. For each decorated_definition → unwrap and route to 5 or 6
        """
        # --- Step 1: materialise source ---
        # text_stream is a lazy line iterator (from stream_file).  We join
        # and encode to UTF-8 bytes because tree-sitter.Parser.parse() expects
        # bytes.  encoding="utf-8" is set on the file open in ingest.py; if a
        # file sneaks in with a BOM, errors="replace" protects us.
        source: bytes = "".join(text_stream).encode("utf-8", errors="replace")

        if not source.strip():
            return  # empty file — nothing to yield

        # --- Step 2: parse ---
        # parse() returns a Tree.  tree.root_node is the top-level `module` node.
        parser = self._get_parser()
        tree = parser.parse(source)
        root: Node = tree.root_node

        # root.type == "module" for a well-formed Python file.
        # named_children skips anonymous tokens (colons, parens, whitespace)
        # and gives us the meaningful statement nodes.
        top_level: list[Node] = root.named_children

        # --- Step 3: preamble ---
        preamble = _collect_preamble_text(top_level, source)
        if preamble is not None:
            text, start, end = preamble
            symbol = SymbolInfo(
                name=self.meta.file_name,   # "domain.py" — the module itself
                kind=SymbolKind.MODULE,
            )
            yield from self.emit(start, end, text, symbol=symbol)

        # --- Step 4: walk top-level definitions ---
        for node in top_level:
            yield from self._handle_top_level(node, source)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _handle_top_level(self, node: Node, source: bytes) -> Iterator[Chunk]:
        """
        Dispatch a single top-level node to the right handler.

        tree-sitter node types we care about:
            function_definition         → def foo():
            decorated_definition        → @deco\ndef foo():  or  @deco\nclass Foo:
            class_definition            → class Foo:

        Everything else (imports, assignments) was already consumed by
        _collect_preamble_text, so we skip it here.
        """
        node_type = node.type

        if node_type == "function_definition":
            yield from self._emit_function(node, source, parent=None)

        elif node_type == "decorated_definition":
            # The decoration sits *outside* the real definition.  Unwrap to
            # discover whether this is a function or class, then handle it.
            inner = _unwrap_decorated(node)
            if inner.type == "function_definition":
                # Pass the *outer* decorated node so the decorator lines are
                # included in the chunk text.
                yield from self._emit_function(node, source, parent=None, name_node=inner)
            elif inner.type == "class_definition":
                class_name = _symbol_name(inner) or "<anonymous>"
                yield from _split_class(node, source, class_name, self.emit)

        elif node_type == "class_definition":
            class_name = _symbol_name(node) or "<anonymous>"
            yield from _split_class(node, source, class_name, self.emit)

        # Skip everything else: imports and module-level assignments belong to
        # the MODULE chunk, not here.

    def _emit_function(
        self,
        node: Node,           # may be decorated_definition or function_definition
        source: bytes,
        parent: str | None,   # set to class name when called for methods
        name_node: Node | None = None,  # override: the actual function_definition
    ) -> Iterator[Chunk]:
        """
        Yield a single FUNCTION chunk for a top-level function.

        `name_node` is provided when `node` is a decorated_definition so we
        can extract the identifier from the inner function_definition while
        still slicing text from the outer node (which includes the decorator).
        """
        # Resolve which node carries the 'name' field.
        defn = name_node if name_node is not None else node
        fn_name = _symbol_name(defn) or "<anonymous>"

        # The chunk text comes from the outermost node (includes decorators).
        text = _node_text(node, source)

        symbol = SymbolInfo(
            name=fn_name,
            kind=SymbolKind.FUNCTION,
            parent=parent,  # None for top-level; set when called from _split_class
        )
        yield from self.emit(_start_line(node), _end_line(node), text, symbol=symbol)
