"""Shared base for tree-sitter-backed parsers.

Centralizes:
  * grammar loading with graceful degradation (missing pip wheels)
  * source-snippet extraction (truncated for large bodies)
  * common helpers: text(), child_by_type(), walk_descendants()
  * a default parse() that walks the tree using language-specific node-type maps
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple, Union

from ckg.core import ParseResult, ParsedEdge, ParsedNode
from ckg.observability import get_logger
from ckg.parsers.base import BaseParser

logger = get_logger(__name__)


# ── Tree-sitter import shim ──────────────────────────────────────────────────
try:
    from tree_sitter import Language, Parser  # type: ignore

    _TS_AVAILABLE = True
except ImportError:  # pragma: no cover
    _TS_AVAILABLE = False
    Language = object  # type: ignore
    Parser = object    # type: ignore


def is_treesitter_available() -> bool:
    return _TS_AVAILABLE


def text_of(node: Any) -> str:
    """Decode a tree-sitter node's bytes to UTF-8 (lossy, never raises)."""
    return node.text.decode("utf-8", errors="replace") if node and node.text else ""


def first_child_of_type(node: Any, *types: str) -> Optional[Any]:
    """First direct child whose ``type`` matches one of ``types``."""
    if node is None:
        return None
    for child in node.children:
        if child.type in types:
            return child
    return None


def walk_descendants(root: Any) -> Iterable[Any]:
    """Iterative DFS, no recursion — safe on huge files."""
    if root is None:
        return
    stack: List[Any] = list(root.children)
    while stack:
        node = stack.pop()
        yield node
        stack.extend(node.children)


def extract_snippet(source_lines: List[str], start: int, end: int, *, max_lines: int = 10) -> str:
    """Compact source snippet — head + tail when the body is long.

    Lines are 0-indexed (tree-sitter convention). End is exclusive.
    """
    if start < 0 or end <= start:
        return ""
    lines = source_lines[start:end]
    if not lines:
        return ""
    if len(lines) <= max_lines:
        return "\n".join(lines).rstrip()
    head = lines[:5]
    tail = lines[-3:]
    return "\n".join(head + [f"    # ... ({len(lines) - 8} more lines)"] + tail).rstrip()


# ── Configuration object for the generic walker ─────────────────────────────
@dataclass
class LanguageSpec:
    """Declarative description of what to extract for a language.

    Subclasses fill this in; the base ``parse`` method does the rest.
    """

    language: str
    # tree-sitter node type → CKG NodeType string. Multiple node types can map
    # to the same NodeType (e.g. Rust's struct_item + union_item → STRUCT).
    class_node_types: Set[str] = field(default_factory=set)
    function_node_types: Set[str] = field(default_factory=set)
    method_node_types: Set[str] = field(default_factory=set)
    interface_node_types: Set[str] = field(default_factory=set)
    enum_node_types: Set[str] = field(default_factory=set)
    type_alias_node_types: Set[str] = field(default_factory=set)
    import_node_types: Set[str] = field(default_factory=set)
    call_node_types: Set[str] = field(default_factory=set)

    # Field name on the node that holds the symbol's identifier — usually "name".
    name_field: str = "name"
    body_field: str = "body"
    parameters_field: str = "parameters"

    # Function used to extract the import path string from an import node.
    extract_import: Optional[Callable[[Any], List[str]]] = None
    # Function used to build a function/method signature string.
    extract_signature: Optional[Callable[[Any], str]] = None
    # Function used to extract a docstring/comment from the body.
    extract_docstring: Optional[Callable[[Any], Optional[str]]] = None


# ── Base class ────────────────────────────────────────────────────────────────
class TreeSitterParser(BaseParser):
    """Generic tree-sitter parser. Subclasses provide a ``LanguageSpec`` + grammar."""

    spec: LanguageSpec

    def __init__(self, ts_language: Any) -> None:
        if not _TS_AVAILABLE:  # pragma: no cover
            raise RuntimeError("tree-sitter not installed")
        self._lang = ts_language
        self._parser = Parser(ts_language)

    # Subclasses override to plug in helpers that depend on the grammar.
    def _signature(self, node: Any) -> Optional[str]:
        if self.spec.extract_signature:
            return self.spec.extract_signature(node)
        name_node = node.child_by_field_name(self.spec.name_field)
        params_node = node.child_by_field_name(self.spec.parameters_field)
        name = text_of(name_node) if name_node else "?"
        params = text_of(params_node) if params_node else "()"
        return f"{name}{params}"

    def _docstring(self, body_node: Any) -> Optional[str]:
        if self.spec.extract_docstring:
            return self.spec.extract_docstring(body_node)
        return None

    def _imports(self, node: Any) -> List[str]:
        if self.spec.extract_import:
            return self.spec.extract_import(node)
        return [text_of(node).strip()]

    # ── The actual parse driver ──────────────────────────────────────────────
    def parse(self, file_path: Union[str, Path], source: str) -> ParseResult:
        fp = str(file_path)
        result = ParseResult(file_path=fp, language=self.spec.language)
        try:
            tree = self._parser.parse(source.encode("utf-8"))
        except Exception as exc:
            result.error = str(exc)
            return result

        source_lines = source.splitlines()
        root = tree.root_node

        # FILE node — every parser emits this so cross-file edges can attach.
        file_node = ParsedNode(
            type="FILE",
            name=Path(fp).name,
            qualified_name=fp,
            file_path=fp,
            start_line=1,
            end_line=root.end_point[0] + 1,
            language=self.spec.language,
        )
        result.nodes.append(file_node)

        self._walk(
            node=root,
            file_path=fp,
            module_qname=fp,
            parent_qname=fp,
            class_qname=None,
            result=result,
            source_lines=source_lines,
        )
        return result

    # ── Walker ───────────────────────────────────────────────────────────────
    def _walk(
        self,
        node: Any,
        *,
        file_path: str,
        module_qname: str,
        parent_qname: str,
        class_qname: Optional[str],
        result: ParseResult,
        source_lines: List[str],
    ) -> None:
        for child in node.children:
            kind = child.type

            if kind in self.spec.import_node_types:
                for raw in self._imports(child):
                    if raw:
                        result.import_paths.append(raw)
                        result.edges.append(
                            ParsedEdge(
                                source_qualified=file_path,
                                target_qualified=raw,
                                type="IMPORTS",
                                file_path=file_path,
                            )
                        )

            elif kind in self.spec.class_node_types | self.spec.interface_node_types | self.spec.enum_node_types:
                node_type = (
                    "CLASS" if kind in self.spec.class_node_types
                    else "INTERFACE" if kind in self.spec.interface_node_types
                    else "ENUM"
                )
                self._handle_class_like(
                    child, node_type=node_type, file_path=file_path,
                    module_qname=module_qname, parent_qname=parent_qname,
                    result=result, source_lines=source_lines,
                )

            elif kind in self.spec.function_node_types:
                self._handle_function(
                    child, node_type="METHOD" if class_qname else "FUNCTION",
                    file_path=file_path, parent_qname=parent_qname,
                    class_qname=class_qname, result=result, source_lines=source_lines,
                )

            elif kind in self.spec.method_node_types:
                self._handle_function(
                    child, node_type="METHOD",
                    file_path=file_path, parent_qname=parent_qname,
                    class_qname=class_qname, result=result, source_lines=source_lines,
                )

            elif kind in self.spec.type_alias_node_types:
                self._handle_type_alias(child, file_path, parent_qname, result)

    def _handle_class_like(
        self,
        node: Any,
        *,
        node_type: str,
        file_path: str,
        module_qname: str,
        parent_qname: str,
        result: ParseResult,
        source_lines: List[str],
    ) -> None:
        name_node = node.child_by_field_name(self.spec.name_field)
        if not name_node:
            return
        name = text_of(name_node)
        qname = f"{module_qname}.{name}"
        body = node.child_by_field_name(self.spec.body_field)
        snippet = extract_snippet(source_lines, node.start_point[0], node.end_point[0] + 1)

        result.nodes.append(
            ParsedNode(
                type=node_type,
                name=name,
                qualified_name=qname,
                file_path=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                docstring=self._docstring(body),
                language=self.spec.language,
                source_snippet=snippet,
            )
        )
        result.edges.append(
            ParsedEdge(
                source_qualified=file_path,
                target_qualified=qname,
                type="DEFINES",
                file_path=file_path,
            )
        )
        # Recurse into the body — methods etc.
        if body:
            self._walk(
                node=body,
                file_path=file_path,
                module_qname=module_qname,
                parent_qname=qname,
                class_qname=qname,
                result=result,
                source_lines=source_lines,
            )

    def _handle_function(
        self,
        node: Any,
        *,
        node_type: str,
        file_path: str,
        parent_qname: str,
        class_qname: Optional[str],
        result: ParseResult,
        source_lines: List[str],
    ) -> None:
        name_node = node.child_by_field_name(self.spec.name_field)
        if not name_node:
            return
        name = text_of(name_node)
        qname = f"{parent_qname}.{name}"
        body = node.child_by_field_name(self.spec.body_field)
        snippet = extract_snippet(source_lines, node.start_point[0], node.end_point[0] + 1)

        result.nodes.append(
            ParsedNode(
                type=node_type,
                name=name,
                qualified_name=qname,
                file_path=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                signature=self._signature(node),
                docstring=self._docstring(body),
                language=self.spec.language,
                source_snippet=snippet,
            )
        )
        result.edges.append(
            ParsedEdge(
                source_qualified=parent_qname,
                target_qualified=qname,
                type="CONTAINS" if class_qname else "DEFINES",
                file_path=file_path,
            )
        )

        # Extract calls from the body so we get a real call graph.
        if body and self.spec.call_node_types:
            for descendant in walk_descendants(body):
                if descendant.type in self.spec.call_node_types:
                    callee = self._extract_callee(descendant)
                    if callee:
                        result.edges.append(
                            ParsedEdge(
                                source_qualified=qname,
                                target_qualified=callee,
                                type="CALLS",
                                file_path=file_path,
                            )
                        )

    def _extract_callee(self, call_node: Any) -> Optional[str]:
        """Default: name comes from the ``function`` field. Subclasses can override."""
        fn = call_node.child_by_field_name("function")
        if fn:
            return text_of(fn)
        return None

    def _handle_type_alias(
        self, node: Any, file_path: str, parent_qname: str, result: ParseResult
    ) -> None:
        name_node = node.child_by_field_name(self.spec.name_field)
        if not name_node:
            return
        name = text_of(name_node)
        qname = f"{parent_qname}.{name}"
        result.nodes.append(
            ParsedNode(
                type="TYPE",
                name=name,
                qualified_name=qname,
                file_path=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                language=self.spec.language,
            )
        )
        result.edges.append(
            ParsedEdge(
                source_qualified=parent_qname,
                target_qualified=qname,
                type="DEFINES",
                file_path=file_path,
            )
        )
