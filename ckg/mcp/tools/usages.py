"""find_usages — every place a symbol is referenced (CALLS / USES / REFERENCES)."""
from __future__ import annotations

from typing import Any, Dict

from ckg.store.base import GraphStore


async def find_usages(store: GraphStore, name: str) -> Dict[str, Any]:
    rows = await store.search_nodes(name, limit=3)
    if not rows:
        return {"query": name, "found": False, "usages": [], "usage_count": 0}

    target = rows[0]
    usages: list[dict] = []
    for edge_type in ("CALLS", "USES", "REFERENCES", "INHERITS", "IMPORTS"):
        users = await store.neighbors(target.id, direction="in", edge_type=edge_type)
        for u in users:
            usages.append(
                {
                    "edge_type": edge_type,
                    "user_name": u.name, "user_qualified_name": u.qualified_name,
                    "user_type": u.type,
                    "file_path": u.file_path, "line": u.start_line,
                    "language": u.language,
                }
            )
    return {
        "query": name, "found": True, "target": target.name,
        "usage_count": len(usages), "usages": usages,
    }
