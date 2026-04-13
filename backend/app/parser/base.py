from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

@dataclass
class ParsedNode:
    type: str
    name: str
    qualified_name: str
    file_path: str
    start_line: int
    end_line: int
    language: str
    signature: Optional[str] = None
    docstring: Optional[str] = None

@dataclass
class ParsedEdge:
    source_qualified: str
    target_qualified: str
    type: str
    file_path: str
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class ParseResult:
    file_path: str
    language: str
    nodes: List[ParsedNode] = field(default_factory=list)
    edges: List[ParsedEdge] = field(default_factory=list)
    import_paths: List[str] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None

class BaseParser:
    language: str = "unknown"
    def parse(self, file_path: str | Path, source: str) -> ParseResult:
        raise NotImplementedError

    def parse_file(self, file_path: str | Path) -> ParseResult:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            return self.parse(file_path, content)
        except Exception as e:
            res = ParseResult(file_path=str(file_path), language=self.language)
            res.error = str(e)
            return res
