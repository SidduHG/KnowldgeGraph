"""Storage Protocol — backends conform to this; the indexer talks only to this.

We use Protocol (PEP 544) instead of an abstract base class so callers can
pass in mocks/fakes for testing without inheritance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Set


@dataclass(slots=True)
class NodeRecord:
    id: str
    type: str
    name: str
    file_path: str
    qualified_name: str = ""
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    signature: Optional[str] = None
    docstring: Optional[str] = None
    source_snippet: Optional[str] = None
    language: Optional[str] = None


@dataclass(slots=True)
class EdgeRecord:
    source_id: str
    target_id: str
    type: str
    file_path: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FileHashRecord:
    path: str
    sha256: str
    size: int = 0
    language: Optional[str] = None


class GraphStore(Protocol):
    """Every backend (SQLite, MySQL, ...) implements this."""

    # ── Lifecycle ────────────────────────────────────────────────────────────
    async def init(self) -> None: ...
    async def close(self) -> None: ...
    async def clear_all(self) -> None: ...

    # ── Nodes ────────────────────────────────────────────────────────────────
    async def upsert_nodes(self, nodes: List[NodeRecord]) -> int: ...
    async def delete_nodes_by_file(self, file_path: str) -> int: ...
    async def list_nodes(
        self,
        *,
        type: Optional[str] = None,
        language: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[NodeRecord]: ...
    async def get_node(self, node_id: str) -> Optional[NodeRecord]: ...
    async def get_nodes_by_file(self, file_path: str) -> List[NodeRecord]: ...
    async def search_nodes(self, query: str, limit: int = 20) -> List[NodeRecord]: ...
    async def get_qname_index(self) -> Dict[str, str]: ...
    async def get_name_index(self) -> Dict[str, List[str]]: ...

    # ── Edges ────────────────────────────────────────────────────────────────
    async def upsert_edges(self, edges: List[EdgeRecord]) -> int: ...
    async def delete_edges_by_file(self, file_path: str) -> int: ...
    async def list_edges(
        self,
        *,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        type: Optional[str] = None,
        limit: int = 100,
    ) -> List[EdgeRecord]: ...
    async def neighbors(
        self,
        node_id: str,
        *,
        direction: str = "out",          # "in" | "out" | "both"
        edge_type: Optional[str] = None,
    ) -> List[NodeRecord]: ...

    # ── File hashes ──────────────────────────────────────────────────────────
    async def get_hash(self, path: str) -> Optional[str]: ...
    async def get_all_hashes(self) -> Dict[str, str]: ...
    async def upsert_hash(self, record: FileHashRecord) -> None: ...
    async def delete_hash(self, path: str) -> None: ...

    # ── File deps ────────────────────────────────────────────────────────────
    async def set_deps(self, importer: str, importees: List[str]) -> None: ...
    async def get_importers(self, importee: str) -> List[str]: ...
    async def get_importees(self, importer: str) -> List[str]: ...
    async def delete_file_deps(self, path: str) -> None: ...
    async def expand_dirty_set(self, dirty: Set[str]) -> Set[str]: ...

    # ── Stats ────────────────────────────────────────────────────────────────
    async def stats(self) -> Dict[str, Any]: ...
