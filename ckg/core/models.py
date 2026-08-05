"""Domain models used throughout the parser → builder → store pipeline.

These are pure data structures — no validation against a DB, no I/O.
All storage backends accept and return these types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class NodeType(str, Enum):
    """Every symbol kind we emit into the graph."""

    FILE = "FILE"
    MODULE = "MODULE"
    CLASS = "CLASS"
    FUNCTION = "FUNCTION"
    METHOD = "METHOD"
    VARIABLE = "VARIABLE"
    TYPE = "TYPE"
    INTERFACE = "INTERFACE"
    ENUM = "ENUM"
    STRUCT = "STRUCT"
    TRAIT = "TRAIT"


class EdgeType(str, Enum):
    """Every relationship kind we emit into the graph."""

    DEFINES = "DEFINES"
    CONTAINS = "CONTAINS"
    IMPORTS = "IMPORTS"
    CALLS = "CALLS"
    INHERITS = "INHERITS"
    IMPLEMENTS = "IMPLEMENTS"
    USES = "USES"
    EXPORTS = "EXPORTS"
    REFERENCES = "REFERENCES"


@dataclass(slots=True)
class ParsedNode:
    """A symbol discovered in a source file by a language parser."""

    type: str
    name: str
    qualified_name: str
    file_path: str
    start_line: int
    end_line: int
    language: str
    signature: Optional[str] = None
    docstring: Optional[str] = None
    source_snippet: Optional[str] = None
    visibility: Optional[str] = None  # public | private | protected | None
    is_async: bool = False
    is_generator: bool = False


@dataclass(slots=True)
class ParsedEdge:
    """A relationship between two qualified-name references."""

    source_qualified: str
    target_qualified: str
    type: str
    file_path: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParseResult:
    """Aggregate output from one parser run on one file."""

    file_path: str
    language: str
    nodes: List[ParsedNode] = field(default_factory=list)
    edges: List[ParsedEdge] = field(default_factory=list)
    import_paths: List[str] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def __repr__(self) -> str:  # nicer test failure messages
        return (
            f"ParseResult({self.file_path!r}, lang={self.language}, "
            f"nodes={len(self.nodes)}, edges={len(self.edges)}, ok={self.ok})"
        )
