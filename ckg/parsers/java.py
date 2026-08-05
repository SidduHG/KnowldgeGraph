"""Java parser via tree-sitter-java."""
from __future__ import annotations

from typing import Any, List

from ckg.observability import get_logger
from ckg.parsers.registry import register
from ckg.parsers.treesitter import LanguageSpec, TreeSitterParser, text_of

logger = get_logger(__name__)

try:
    from tree_sitter import Language  # type: ignore
    import tree_sitter_java as tsjava  # type: ignore

    _JAVA_LANGUAGE = Language(tsjava.language())
    _AVAILABLE = True
except ImportError:  # pragma: no cover
    _AVAILABLE = False
    _JAVA_LANGUAGE = None
    logger.info("tree-sitter-java not installed — Java parsing disabled")


def _java_imports(node: Any) -> List[str]:
    out: List[str] = []
    if node.type == "import_declaration":
        # find the qualified-name child
        for child in node.children:
            if child.type in ("scoped_identifier", "identifier"):
                out.append(text_of(child))
    return out


@register("java")
class JavaParser(TreeSitterParser):
    spec = LanguageSpec(
        language="java",
        class_node_types={"class_declaration"},
        function_node_types={"method_declaration"},
        method_node_types={"method_declaration"},
        interface_node_types={"interface_declaration"},
        enum_node_types={"enum_declaration"},
        import_node_types={"import_declaration"},
        call_node_types={"method_invocation"},
        name_field="name",
        body_field="body",
        parameters_field="parameters",
        extract_import=_java_imports,
    )

    def __init__(self) -> None:
        if not _AVAILABLE:  # pragma: no cover
            raise RuntimeError("tree-sitter-java not available")
        super().__init__(_JAVA_LANGUAGE)
