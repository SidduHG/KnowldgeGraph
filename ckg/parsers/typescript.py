"""TypeScript / JavaScript parser.

Both share enough grammar that we use the TypeScript grammar for both —
this matches the original implementation's behavior.
"""
from __future__ import annotations

from typing import Any, List, Optional

from ckg.observability import get_logger
from ckg.parsers.registry import register
from ckg.parsers.treesitter import LanguageSpec, TreeSitterParser, text_of

logger = get_logger(__name__)

try:
    from tree_sitter import Language  # type: ignore
    import tree_sitter_typescript as tsts  # type: ignore

    _TS_LANGUAGE = Language(tsts.language_typescript())
    _TSX_LANGUAGE = Language(tsts.language_tsx())
    _AVAILABLE = True
except ImportError:  # pragma: no cover
    _AVAILABLE = False
    _TS_LANGUAGE = None
    _TSX_LANGUAGE = None
    logger.warning("tree-sitter-typescript not installed; TS/JS parsing disabled")


def _ts_imports(node: Any) -> List[str]:
    out: List[str] = []
    if node.type == "import_statement":
        # The string literal child holds the module path
        for child in node.children:
            if child.type == "string":
                out.append(text_of(child).strip("'\"`"))
    return out


def _ts_signature(node: Any) -> Optional[str]:
    name_node = node.child_by_field_name("name")
    params_node = node.child_by_field_name("parameters")
    name = text_of(name_node) if name_node else "?"
    params = text_of(params_node) if params_node else "()"
    return_type = node.child_by_field_name("return_type")
    return_str = f": {text_of(return_type)}" if return_type else ""
    return f"{name}{params}{return_str}"


def _ts_docstring(body_node: Any) -> Optional[str]:
    """Best-effort: pick up a leading // or /* */ comment within the body.

    Real JSDoc is attached as a sibling, but the tree-sitter API doesn't expose
    leading-trivia neatly — this returns None for now to avoid false positives.
    """
    return None


@register("typescript")
class TypeScriptParser(TreeSitterParser):
    spec = LanguageSpec(
        language="typescript",
        class_node_types={"class_declaration", "abstract_class_declaration"},
        function_node_types={"function_declaration", "function_expression"},
        method_node_types={"method_definition"},
        interface_node_types={"interface_declaration"},
        enum_node_types={"enum_declaration"},
        type_alias_node_types={"type_alias_declaration"},
        import_node_types={"import_statement"},
        call_node_types={"call_expression"},
        name_field="name",
        body_field="body",
        parameters_field="parameters",
        extract_signature=_ts_signature,
        extract_docstring=_ts_docstring,
        extract_import=_ts_imports,
    )

    def __init__(self) -> None:
        if not _AVAILABLE:  # pragma: no cover
            raise RuntimeError("tree-sitter-typescript not available")
        super().__init__(_TS_LANGUAGE)


@register("javascript")
class JavaScriptParser(TypeScriptParser):
    """JS reuses the TypeScript grammar (TS is a superset)."""

    spec = LanguageSpec(
        **{**TypeScriptParser.spec.__dict__, "language": "javascript"}
    )
