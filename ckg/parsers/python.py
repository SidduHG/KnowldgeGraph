"""Python parser — tree-sitter grammar.

Extracts: classes, functions, methods, module variables, imports, calls,
inheritance edges, docstrings, signatures, source snippets.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional, Union

from ckg.core import ParseResult, ParsedEdge, ParsedNode
from ckg.observability import get_logger
from ckg.parsers.registry import register
from ckg.parsers.treesitter import (
    LanguageSpec,
    TreeSitterParser,
    extract_snippet,
    text_of,
    walk_descendants,
)

logger = get_logger(__name__)

try:
    from tree_sitter import Language  # type: ignore
    import tree_sitter_python as tspython  # type: ignore

    _PY_LANGUAGE = Language(tspython.language())
    _AVAILABLE = True
except ImportError:  # pragma: no cover
    _AVAILABLE = False
    _PY_LANGUAGE = None
    logger.warning("tree-sitter-python not installed; Python parsing disabled")


def _py_signature(node: Any) -> str:
    name_node = node.child_by_field_name("name")
    params_node = node.child_by_field_name("parameters")
    name = text_of(name_node) if name_node else "?"
    params = text_of(params_node) if params_node else "()"
    ret_node = node.child_by_field_name("return_type")
    suffix = f" -> {text_of(ret_node)}" if ret_node else ""
    return f"{name}{params}{suffix}"


def _py_docstring(body_node: Any) -> Optional[str]:
    if body_node is None:
        return None
    for child in body_node.children:
        if child.type == "expression_statement":
            inner = child.children[0] if child.children else None
            if inner and inner.type in ("string", "concatenated_string"):
                return text_of(inner).strip("'\"").strip()
    return None


def _py_imports(node: Any) -> List[str]:
    """Extract dotted module names from ``import_statement`` / ``import_from_statement``."""
    out: List[str] = []
    if node.type == "import_statement":
        for child in node.children:
            if child.type in ("dotted_name", "aliased_import"):
                name = child.child_by_field_name("name") or child
                out.append(text_of(name))
    elif node.type == "import_from_statement":
        module = node.child_by_field_name("module_name")
        if module:
            out.append(text_of(module))
    return out


@register("python")
class PythonParser(TreeSitterParser):
    """tree-sitter-python adapter.

    Inheritance edges and module variables aren't expressible via the generic
    walker — we override ``parse`` to layer them on top.
    """

    spec = LanguageSpec(
        language="python",
        class_node_types={"class_definition"},
        function_node_types={"function_definition"},
        method_node_types=set(),  # we detect method-vs-function by parent context
        import_node_types={"import_statement", "import_from_statement"},
        call_node_types={"call"},
        type_alias_node_types={"type_alias_statement"},
        name_field="name",
        body_field="body",
        parameters_field="parameters",
        extract_signature=_py_signature,
        extract_docstring=_py_docstring,
        extract_import=_py_imports,
    )

    def __init__(self) -> None:
        if not _AVAILABLE:  # pragma: no cover
            raise RuntimeError("tree-sitter-python not available")
        super().__init__(_PY_LANGUAGE)

    # The default ``parse`` from the base handles 95% of the cases. We override
    # so we can additionally emit INHERITS edges and module-level VARIABLE nodes.
    def parse(self, file_path: Union[str, Path], source: str) -> ParseResult:
        result = super().parse(file_path, source)
        if not result.ok:
            return result

        fp = str(file_path)
        tree = self._parser.parse(source.encode("utf-8"))
        # INHERITS edges (CLASS → CLASS by name)
        for cls in walk_descendants(tree.root_node):
            if cls.type == "class_definition":
                name_node = cls.child_by_field_name("name")
                if not name_node:
                    continue
                cls_qname = self._class_qname(cls, fp)
                supers = cls.child_by_field_name("superclasses")
                if supers:
                    for arg in supers.children:
                        if arg.type in ("identifier", "attribute"):
                            result.edges.append(
                                ParsedEdge(
                                    source_qualified=cls_qname,
                                    target_qualified=text_of(arg),
                                    type="INHERITS",
                                    file_path=fp,
                                )
                            )

        # Module-level assignments → VARIABLE nodes.
        for child in tree.root_node.children:
            if child.type == "expression_statement":
                inner = child.children[0] if child.children else None
                if inner and inner.type == "assignment":
                    lhs = inner.child_by_field_name("left")
                    if lhs and lhs.type == "identifier":
                        name = text_of(lhs)
                        qname = f"{fp}.{name}"
                        result.nodes.append(
                            ParsedNode(
                                type="VARIABLE",
                                name=name,
                                qualified_name=qname,
                                file_path=fp,
                                start_line=inner.start_point[0] + 1,
                                end_line=inner.end_point[0] + 1,
                                language="python",
                            )
                        )
                        result.edges.append(
                            ParsedEdge(
                                source_qualified=fp,
                                target_qualified=qname,
                                type="DEFINES",
                                file_path=fp,
                            )
                        )

        return result

    @staticmethod
    def _class_qname(cls_node: Any, file_path: str) -> str:
        name = text_of(cls_node.child_by_field_name("name"))
        return f"{file_path}.{name}"
