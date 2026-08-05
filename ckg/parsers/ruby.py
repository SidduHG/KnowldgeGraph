"""Ruby parser via tree-sitter-ruby."""
from __future__ import annotations

from typing import Any, List

from ckg.observability import get_logger
from ckg.parsers.registry import register
from ckg.parsers.treesitter import LanguageSpec, TreeSitterParser, text_of

logger = get_logger(__name__)

try:
    from tree_sitter import Language  # type: ignore
    import tree_sitter_ruby as tsruby  # type: ignore

    _RUBY_LANGUAGE = Language(tsruby.language())
    _AVAILABLE = True
except ImportError:  # pragma: no cover
    _AVAILABLE = False
    _RUBY_LANGUAGE = None
    logger.info("tree-sitter-ruby not installed — Ruby parsing disabled")


def _ruby_imports(node: Any) -> List[str]:
    """``require`` / ``require_relative`` calls."""
    out: List[str] = []
    if node.type == "call":
        method = node.child_by_field_name("method")
        if method and text_of(method) in ("require", "require_relative", "load"):
            args = node.child_by_field_name("arguments")
            if args:
                for arg in args.children:
                    if arg.type == "string":
                        out.append(text_of(arg).strip("'\""))
    return out


@register("ruby")
class RubyParser(TreeSitterParser):
    spec = LanguageSpec(
        language="ruby",
        class_node_types={"class"},
        function_node_types={"method"},
        method_node_types={"method", "singleton_method"},
        interface_node_types={"module"},
        import_node_types={"call"},  # filtered inside _ruby_imports
        call_node_types={"call"},
        name_field="name",
        body_field="body",
        parameters_field="parameters",
        extract_import=_ruby_imports,
    )

    def __init__(self) -> None:
        if not _AVAILABLE:  # pragma: no cover
            raise RuntimeError("tree-sitter-ruby not available")
        super().__init__(_RUBY_LANGUAGE)
