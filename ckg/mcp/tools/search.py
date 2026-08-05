"""Fuzzy symbol search across the entire graph."""
from __future__ import annotations

from typing import Any, Dict, Optional

from ckg.store.base import GraphStore


async def search_symbol(
    store: GraphStore, query: str, type: Optional[str] = None, limit: int = 20
) -> Dict[str, Any]:
    rows = await store.search_nodes(query, limit=limit)
    if type:
        rows = [r for r in rows if r.type == type.upper()]
    return {
        "query": query,
        "type_filter": type,
        "count": len(rows),
        "results": [
            {
                "type": r.type, "name": r.name, "qualified_name": r.qualified_name,
                "file_path": r.file_path, "start_line": r.start_line,
                "signature": r.signature, "language": r.language,
            }
            for r in rows
        ],
    }
