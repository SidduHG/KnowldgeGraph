"""impact_analysis — compute the transitive blast radius of changing a symbol.

Walks the inverse call/use graph until either depth ``max_depth`` is reached
or the frontier shrinks to empty. Returns the set of files that would need
re-checking, grouped by hop distance.
"""
from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Set

from ckg.store.base import GraphStore


async def impact_analysis(
    store: GraphStore, name: str, *, max_depth: int = 3
) -> Dict[str, Any]:
    rows = await store.search_nodes(name, limit=3)
    if not rows:
        return {"query": name, "found": False}

    seed = rows[0]
    visited: Set[str] = {seed.id}
    impacted_files: Set[str] = {seed.file_path}
    by_hop: List[Dict[str, Any]] = []
    frontier: deque[str] = deque([seed.id])

    for hop in range(max_depth):
        layer_users: List[Dict[str, Any]] = []
        next_frontier: List[str] = []
        while frontier:
            nid = frontier.popleft()
            for et in ("CALLS", "USES", "INHERITS", "REFERENCES"):
                users = await store.neighbors(nid, direction="in", edge_type=et)
                for u in users:
                    if u.id in visited:
                        continue
                    visited.add(u.id)
                    impacted_files.add(u.file_path)
                    next_frontier.append(u.id)
                    layer_users.append(
                        {
                            "name": u.name,
                            "qualified_name": u.qualified_name,
                            "type": u.type,
                            "file_path": u.file_path,
                            "line": u.start_line,
                            "edge_type": et,
                        }
                    )
        by_hop.append({"hop": hop + 1, "count": len(layer_users), "users": layer_users})
        frontier = deque(next_frontier)
        if not frontier:
            break

    return {
        "query": name,
        "found": True,
        "seed": {
            "name": seed.name, "qualified_name": seed.qualified_name,
            "file_path": seed.file_path, "type": seed.type,
        },
        "max_depth": max_depth,
        "impacted_symbol_count": len(visited) - 1,
        "impacted_file_count": len(impacted_files),
        "impacted_files": sorted(impacted_files),
        "by_hop": by_hop,
    }
