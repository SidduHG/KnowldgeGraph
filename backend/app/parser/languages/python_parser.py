from __future__ import annotations
import logging
from pathlib import Path
from typing import List, Optional, Tuple

from app.parser.base import BaseParser, ParseResult, ParsedEdge, ParsedNode

logger = logging.getLogger(__name__)

try:
    from tree_sitter import Language, Parser as TSParser, Node
    import tree_sitter_python as tspython
    PY_LANGUAGE = Language(tspython.language())
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False
    logger.warning("tree-sitter-python not installed; Python parsing disabled")


def _text(node: "Node") -> str:
    return node.text.decode("utf-8", errors="replace")


def _first_child_of_type(node: "Node", *types: str) -> Optional["Node"]:
    for child in node.children:
        if child.type in types:
            return child
    return None


def _extract_docstring(body_node: "Node") -> Optional[str]:
    """Extract first expression_statement string from a body."""
    if body_node is None:
        return None
    for child in body_node.children:
        if child.type == "expression_statement":
            inner = child.children[0] if child.children else None
            if inner and inner.type in ("string", "concatenated_string"):
                raw = _text(inner)
                return raw.strip("'\"").strip()
    return None


def _build_signature(fn_node: "Node") -> str:
    """Reconstruct function signature (name + params)."""
    name_node = fn_node.child_by_field_name("name")
    params_node = fn_node.child_by_field_name("parameters")
    name = _text(name_node) if name_node else "?"
    params = _text(params_node) if params_node else "()"
    return_node = fn_node.child_by_field_name("return_type")
    ret = f" -> {_text(return_node)}" if return_node else ""
    return f"{name}{params}{ret}"


class PythonParser(BaseParser):
    language = "python"

    def __init__(self) -> None:
        if not _AVAILABLE:
            raise RuntimeError("tree-sitter-python not available")
        self._parser = TSParser(PY_LANGUAGE)

    def parse(self, file_path: str | Path, source: str) -> ParseResult:
        fp = str(file_path)
        result = ParseResult(file_path=fp, language="python")

        try:
            tree = self._parser.parse(source.encode("utf-8"))
        except Exception as exc:
            result.error = str(exc)
            return result

        # ── FILE node ─────────────────────────────────────────────────────────
        file_name = Path(fp).stem
        file_qname = fp
        file_node = ParsedNode(
            type="FILE",
            name=Path(fp).name,
            qualified_name=file_qname,
            file_path=fp,
            start_line=1,
            end_line=tree.root_node.end_point[0] + 1,
            language="python",
        )
        result.nodes.append(file_node)

        # ── Walk top-level nodes ──────────────────────────────────────────────
        self._walk(tree.root_node, fp, file_qname, result, parent_qname=file_qname)
        return result

    def _walk(
        self,
        root: "Node",
        fp: str,
        module_qname: str,
        result: ParseResult,
        parent_qname: str,
        class_qname: Optional[str] = None,
    ) -> None:
        for node in root.children:
            if node.type == "import_statement":
                self._handle_import(node, fp, result)

            elif node.type == "import_from_statement":
                self._handle_import_from(node, fp, result)

            elif node.type == "class_definition":
                self._handle_class(node, fp, module_qname, parent_qname, result)

            elif node.type == "function_definition":
                is_method = class_qname is not None
                self._handle_function(
                    node, fp, parent_qname, result,
                    node_type="METHOD" if is_method else "FUNCTION",
                    class_qname=class_qname,
                )

            elif node.type in ("expression_statement", "assignment", "annotated_assignment"):
                self._handle_variable(node, fp, parent_qname, result)

    def _handle_import(self, node: "Node", fp: str, result: ParseResult) -> None:
        for child in node.children:
            if child.type in ("dotted_name", "aliased_import"):
                name_node = child.child_by_field_name("name") or child
                result.import_paths.append(_text(name_node))

    def _handle_import_from(self, node: "Node", fp: str, result: ParseResult) -> None:
        module_node = node.child_by_field_name("module_name")
        if module_node:
            result.import_paths.append(_text(module_node))

    def _handle_class(
        self,
        node: "Node",
        fp: str,
        module_qname: str,
        parent_qname: str,
        result: ParseResult,
    ) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _text(name_node)
        qname = f"{module_qname}.{name}"
        body = node.child_by_field_name("body")
        doc = _extract_docstring(body)

        class_rec = ParsedNode(
            type="CLASS",
            name=name,
            qualified_name=qname,
            file_path=fp,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            docstring=doc,
            language="python",
        )
        result.nodes.append(class_rec)
        result.edges.append(
            ParsedEdge(source_qualified=fp, target_qualified=qname, type="DEFINES", file_path=fp)
        )

        # Superclasses → INHERITS edges
        args = node.child_by_field_name("superclasses")
        if args:
            for arg in args.children:
                if arg.type in ("identifier", "attribute"):
                    result.edges.append(
                        ParsedEdge(source_qualified=qname, target_qualified=_text(arg),
                                   type="INHERITS", file_path=fp)
                    )

        # Walk class body for methods
        if body:
            self._walk(body, fp, module_qname, result,
                       parent_qname=qname, class_qname=qname)

    def _handle_function(
        self,
        node: "Node",
        fp: str,
        parent_qname: str,
        result: ParseResult,
        node_type: str,
        class_qname: Optional[str],
    ) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _text(name_node)
        qname = f"{parent_qname}.{name}"
        sig = _build_signature(node)
        body = node.child_by_field_name("body")
        doc = _extract_docstring(body)

        fn_rec = ParsedNode(
            type=node_type,
            name=name,
            qualified_name=qname,
            file_path=fp,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=sig,
            docstring=doc,
            language="python",
        )
        result.nodes.append(fn_rec)
        result.edges.append(
            ParsedEdge(source_qualified=parent_qname, target_qualified=qname,
                       type="CONTAINS" if class_qname else "DEFINES", file_path=fp)
        )

        # Scan body for CALLS edges
        if body:
            self._extract_calls(body, qname, fp, result)

    def _handle_variable(
        self,
        node: "Node",
        fp: str,
        parent_qname: str,
        result: ParseResult,
    ) -> None:
        """Only capture module-level and class-level assignments."""
        if node.type == "assignment":
            lhs = node.child_by_field_name("left")
            if lhs and lhs.type == "identifier":
                name = _text(lhs)
                qname = f"{parent_qname}.{name}"
                result.nodes.append(
                    ParsedNode(
                        type="VARIABLE",
                        name=name,
                        qualified_name=qname,
                        file_path=fp,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        language="python",
                    )
                )
                result.edges.append(
                    ParsedEdge(source_qualified=parent_qname, target_qualified=qname,
                               type="DEFINES", file_path=fp)
                )

    def _extract_calls(
        self, body: "Node", caller_qname: str, fp: str, result: ParseResult
    ) -> None:
        """Walk function body and collect call_expression nodes."""
        queue = list(body.children)
        while queue:
            node = queue.pop()
            if node.type == "call":
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
