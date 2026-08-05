"""Rust parser via tree-sitter-rust."""
from __future__ import annotations

from typing import Any, List

from ckg.observability import get_logger
from ckg.parsers.registry import register
from ckg.parsers.treesitter import LanguageSpec, TreeSitterParser, text_of

logger = get_logger(__name__)

try:
    from tree_sitter import Language  # type: ignore
    import tree_sitter_rust as tsrust  # type: ignore

    _RUST_LANGUAGE = Language(tsrust.language())
    _AVAILABLE = True
except ImportError:  # pragma: no cover
    _AVAILABLE = False
    _RUST_LANGUAGE = None
    logger.info("tree-sitter-rust not installed — Rust parsing disabled")


def _rust_imports(node: Any) -> List[str]:
    """``use`` declarations — capture the path text."""
    out: List[str] = []
    if node.type == "use_declaration":
        path_node = node.child_by_field_name("argument") or node.children[1] if len(node.children) > 1 else None
        if path_node:
            out.append(text_of(path_node))
    return out


@register("rust")
class RustParser(TreeSitterParser):
    spec = LanguageSpec(
        language="rust",
        class_node_types={"struct_item", "union_item"},
        function_node_types={"function_item"},
        method_node_types={"function_item"},  # impl-block functions
        interface_node_types={"trait_item"},
        enum_node_types={"enum_item"},
        type_alias_node_types={"type_item"},
        import_node_types={"use_declaration"},
        call_node_types={"call_expression"},
        name_field="name",
        body_field="body",
        parameters_field="parameters",
        extract_import=_rust_imports,
    )

    def __init__(self) -> None:
        if not _AVAILABLE:  # pragma: no cover
            raise RuntimeError("tree-sitter-rust not available")
        super().__init__(_RUST_LANGUAGE)
