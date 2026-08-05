from __future__ import annotations
import logging
from pathlib import Path
from typing import List, Optional

from app.parser.base import BaseParser, ParseResult, ParsedEdge, ParsedNode

logger = logging.getLogger(__name__)

try:
    from tree_sitter import Language, Parser as TSParser, Node
    import tree_sitter_typescript as tsts
    TS_LANGUAGE = Language(tsts.language_typescript())
    TSX_LANGUAGE = Language(tsts.language_tsx())
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False
    logger.warning("tree-sitter-typescript not installed; TS/JS parsing disabled")


def _text(node: "Node") -> str:
    return node.text.decode("utf-8", errors="replace")


def _child_of_type(node: "Node", *types: str) -> Optional["Node"]:
    for child in node.children:
        if child.type in types:
            return child
    return None


def _extract_jsdoc(node: "Node") -> Optional[str]:
    """Look for a comment sibling before this node."""
    prev = node.prev_named_sibling
    if prev and prev.type == "comment":
        raw = _text(prev)
        return raw.lstrip("/*! ").rstrip("/ ").strip()
    return None


def _extract_snippet(source_lines: List[str], start: int, end: int, max_lines: int = 10) -> str:
    """
    Extract a compact source snippet from a node.
    - For short nodes (<=max_lines), return the full source.
    - For long nodes, return first 5 + last 3 lines with '...' separator.
    """
    lines = source_lines[start:end]
    if not lines:
        return ""
    if len(lines) <= max_lines:
        return "\n".join(lines).rstrip()
    head = lines[:5]
    tail = lines[-3:]
    return "\n".join(head + [f"    // ... ({len(lines) - 8} more lines)"] + tail).rstrip()


class TypeScriptParser(BaseParser):
    language = "typescript"

    def __init__(self, tsx: bool = False) -> None:
        if not _AVAILABLE:
            raise RuntimeError("tree-sitter-typescript not available")
        lang = TSX_LANGUAGE if tsx else TS_LANGUAGE
        self._parser = TSParser(lang)
        self._tsx = tsx

    def parse(self, file_path: str | Path, source: str) -> ParseResult:
        fp = str(file_path)
        result = ParseResult(file_path=fp, language="typescript")

        try:
            tree = self._parser.parse(source.encode("utf-8"))
        except Exception as exc:
            result.error = str(exc)
            return result

        source_lines = source.splitlines()

        # FILE node
        result.nodes.append(
            ParsedNode(
                type="FILE",
                name=Path(fp).name,
                qualified_name=fp,
                file_path=fp,
                start_line=1,
                end_line=tree.root_node.end_point[0] + 1,
                language="typescript",
            )
        )

        self._walk(tree.root_node, fp, fp, result, source_lines=source_lines)
        return result

    def _walk(
        self,
        root: "Node",
        fp: str,
        module_qname: str,
        result: ParseResult,
        class_qname: Optional[str] = None,
        source_lines: List[str] = None,
    ) -> None:
        for node in root.children:
            t = node.type

            if t in ("import_declaration", "import_statement"):
                self._handle_import(node, fp, module_qname, result)

            elif t in ("export_statement",):
                self._handle_export(node, fp, module_qname, result, class_qname, source_lines)

            elif t in ("class_declaration", "abstract_class_declaration", "class"):
                self._handle_class(node, fp, module_qname, result, source_lines)

            elif t in (
                "function_declaration", "function",
                "generator_function_declaration", "arrow_function",
            ):
                self._handle_function(node, fp, module_qname, result,
                                      "METHOD" if class_qname else "FUNCTION",
                                      class_qname, source_lines)

            elif t in ("lexical_declaration", "variable_declaration"):
                self._handle_variable(node, fp, module_qname, result, source_lines)

            elif t == "method_definition":
                self._handle_method(node, fp, module_qname, result, class_qname, source_lines)

            elif t in ("interface_declaration", "type_alias_declaration"):
                self._handle_type(node, fp, module_qname, result, source_lines)

    def _handle_import(self, node: "Node", fp: str, module_qname: str, result: ParseResult) -> None:
        src = node.child_by_field_name("source")
        if src:
            raw = _text(src).strip("'\"")
            result.import_paths.append(raw)

            # Extract named imports for cross-file IMPORTS edges
            for child in node.children:
                if child.type == "import_clause":
                    for sub in child.children:
                        if sub.type == "named_imports":
                            for spec in sub.children:
                                if spec.type == "import_specifier":
                                    name_node = spec.child_by_field_name("name")
                                    if name_node:
                                        imported_name = _text(name_node)
                                        result.edges.append(
                                            ParsedEdge(
                                                source_qualified=fp,
                                                target_qualified=f"{raw}.{imported_name}",
                                                type="IMPORTS",
                                                file_path=fp,
                                            )
                                        )
                        elif sub.type == "identifier":
                            # Default import
                            result.edges.append(
                                ParsedEdge(
                                    source_qualified=fp,
                                    target_qualified=f"{raw}.default",
                                    type="IMPORTS",
                                    file_path=fp,
                                )
                            )

    def _handle_export(
        self,
        node: "Node",
        fp: str,
        module_qname: str,
        result: ParseResult,
        class_qname: Optional[str],
        source_lines: List[str] = None,
    ) -> None:
        # Recurse into exported declaration
        for child in node.children:
            if child.type not in ("export", "default", "comment"):
                self._walk(
                    child.__class__(child._node) if hasattr(child, "_node") else child,
                    fp, module_qname, result, class_qname, source_lines
                )
                # Add EXPORTS edge for named exports
                name_node = child.child_by_field_name("name")
                if name_node:
                    qname = f"{module_qname}.{_text(name_node)}"
                    result.edges.append(
                        ParsedEdge(source_qualified=fp, target_qualified=qname,
                                   type="EXPORTS", file_path=fp)
                    )

    def _handle_class(
        self, node: "Node", fp: str, module_qname: str, result: ParseResult,
        source_lines: List[str] = None,
    ) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _text(name_node)
        qname = f"{module_qname}.{name}"
        doc = _extract_jsdoc(node)

        snippet = None
        if source_lines:
            snippet = _extract_snippet(source_lines, node.start_point[0], node.end_point[0] + 1)

        result.nodes.append(
            ParsedNode(
                type="CLASS",
                name=name,
                qualified_name=qname,
                file_path=fp,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                docstring=doc,
                language="typescript",
                source_snippet=snippet,
            )
        )
        result.edges.append(
            ParsedEdge(source_qualified=fp, target_qualified=qname, type="DEFINES", file_path=fp)
        )

        # Superclass
        heritage = node.child_by_field_name("heritage")
        if heritage:
            for clause in heritage.children:
                if clause.type == "extends_clause":
                    for ch in clause.children:
                        if ch.type in ("identifier", "member_expression"):
                            result.edges.append(
                                ParsedEdge(source_qualified=qname,
                                           target_qualified=_text(ch),
                                           type="INHERITS", file_path=fp)
                            )

        # Walk class body
        body = node.child_by_field_name("body")
        if body:
            self._walk(body, fp, module_qname, result,
                       class_qname=qname, source_lines=source_lines)

    def _handle_function(
        self,
        node: "Node",
        fp: str,
        parent_qname: str,
        result: ParseResult,
        node_type: str,
        class_qname: Optional[str],
        source_lines: List[str] = None,
    ) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _text(name_node)
        qname = f"{parent_qname}.{name}"
        doc = _extract_jsdoc(node)
        params = node.child_by_field_name("parameters")
        sig = f"{name}{_text(params) if params else '()'}"

        snippet = None
        if source_lines:
            snippet = _extract_snippet(source_lines, node.start_point[0], node.end_point[0] + 1)

        result.nodes.append(
            ParsedNode(
                type=node_type,
                name=name,
                qualified_name=qname,
                file_path=fp,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                signature=sig,
                docstring=doc,
                language="typescript",
                source_snippet=snippet,
            )
        )
        result.edges.append(
            ParsedEdge(
                source_qualified=parent_qname,
                target_qualified=qname,
                type="CONTAINS" if class_qname else "DEFINES",
                file_path=fp,
            )
        )

        body = node.child_by_field_name("body")
        if body:
            self._extract_calls(body, qname, fp, result)

    def _handle_method(
        self,
        node: "Node",
        fp: str,
        module_qname: str,
        result: ParseResult,
        class_qname: Optional[str],
        source_lines: List[str] = None,
    ) -> None:
        parent = class_qname or module_qname
        self._handle_function(node, fp, parent, result, "METHOD", class_qname, source_lines)

    def _handle_variable(
        self, node: "Node", fp: str, module_qname: str, result: ParseResult,
        source_lines: List[str] = None,
    ) -> None:
        for decl in node.children:
            if decl.type == "variable_declarator":
                name_node = decl.child_by_field_name("name")
                if name_node and name_node.type == "identifier":
                    name = _text(name_node)
                    qname = f"{module_qname}.{name}"

                    # Check if the value is an arrow function → treat as FUNCTION
                    value = decl.child_by_field_name("value")
                    if value and value.type == "arrow_function":
                        params = value.child_by_field_name("parameters")
                        sig = f"{name}{_text(params) if params else '()'}"
                        snippet = None
                        if source_lines:
                            snippet = _extract_snippet(
                                source_lines, node.start_point[0], node.end_point[0] + 1
                            )
                        result.nodes.append(
                            ParsedNode(
                                type="FUNCTION",
                                name=name,
                                qualified_name=qname,
                                file_path=fp,
                                start_line=node.start_point[0] + 1,
                                end_line=node.end_point[0] + 1,
                                signature=sig,
                                language="typescript",
                                source_snippet=snippet,
                            )
                        )
                        result.edges.append(
                            ParsedEdge(source_qualified=module_qname, target_qualified=qname,
                                       type="DEFINES", file_path=fp)
                        )
                        # Extract calls from arrow function body
                        body = value.child_by_field_name("body")
                        if body:
                            self._extract_calls(body, qname, fp, result)
                    else:
                        result.nodes.append(
                            ParsedNode(
                                type="VARIABLE",
                                name=name,
                                qualified_name=qname,
                                file_path=fp,
                                start_line=node.start_point[0] + 1,
                                end_line=node.end_point[0] + 1,
                                language="typescript",
                            )
                        )
                        result.edges.append(
                            ParsedEdge(source_qualified=module_qname, target_qualified=qname,
                                       type="DEFINES", file_path=fp)
                        )

    def _handle_type(
        self, node: "Node", fp: str, module_qname: str, result: ParseResult,
        source_lines: List[str] = None,
    ) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _text(name_node)
        qname = f"{module_qname}.{name}"

        snippet = None
        if source_lines:
            snippet = _extract_snippet(source_lines, node.start_point[0], node.end_point[0] + 1)

        result.nodes.append(
            ParsedNode(
                type="TYPE",
                name=name,
                qualified_name=qname,
                file_path=fp,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                language="typescript",
                source_snippet=snippet,
            )
        )
        result.edges.append(
            ParsedEdge(source_qualified=fp, target_qualified=qname, type="DEFINES", file_path=fp)
        )

    def _extract_calls(
        self, body: "Node", caller_qname: str, fp: str, result: ParseResult
    ) -> None:
        queue = list(body.children)
        while queue:
            node = queue.pop()
            if node.type == "call_expression":
                fn_node = node.child_by_field_name("function")
                if fn_node:
                    result.edges.append(
                        ParsedEdge(
                            source_qualified=caller_qname,
                            target_qualified=_text(fn_node),
                            type="CALLS",
                            file_path=fp,
                        )
                    )
            queue.extend(node.children)
