"""Go parser via tree-sitter-go."""
from __future__ import annotations

from typing import Any, List

from ckg.observability import get_logger
from ckg.parsers.registry import register
from ckg.parsers.treesitter import LanguageSpec, TreeSitterParser, text_of

logger = get_logger(__name__)

try:
    from tree_sitter import Language  # type: ignore
    import tree_sitter_go as tsgo  # type: ignore

    _GO_LANGUAGE = Language(tsgo.language())
    _AVAILABLE = True
except ImportError:  # pragma: no cover
    _AVAILABLE = False
    _GO_LANGUAGE = None
    logger.info("tree-sitter-go not installed — Go parsing disabled")


def _go_imports(node: Any) -> List[str]:
    """Both ``import_declaration`` and ``import_spec_list`` need to be unwrapped."""
    out: List[str] = []
    if node.type == "import_declaration":
        # walk to find import_spec → interpreted_string_literal
        stack = list(node.children)
        while stack:
            child = stack.pop()
            if child.type == "interpreted_string_literal":
                out.append(text_of(child).strip('"`'))
            else:
                stack.extend(child.children)
    return out


@register("go")
class GoParser(TreeSitterParser):
    spec = LanguageSpec(
        language="go",
        class_node_types={"type_declaration"},  # struct/interface live inside
        function_node_types={"function_declaration"},
        method_node_types={"method_declaration"},
        import_node_types={"import_declaration"},
        call_node_types={"call_expression"},
        name_field="name",
        body_field="body",
        parameters_field="parameters",
        extract_import=_go_imports,
    )

    def __init__(self) -> None:
        if not _AVAILABLE:  # pragma: no cover
            raise RuntimeError("tree-sitter-go not available")
        super().__init__(_GO_LANGUAGE)
