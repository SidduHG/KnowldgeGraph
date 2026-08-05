"""get_subgraph — N-hop neighbourhood for arbitrary edge types.

The escape-hatch tool: lets the agent ask for any subgraph it wants when
the more specific tools don't cover the use case.
"""
from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Optional, Set

from ckg.store.base import GraphStore


async def get_subgraph(
    store: GraphStore,
    name: str,
    *,
    depth: int = 2,
    edge_types: Optional[List[str]] = None,
    direction: str = "both",
) -> Dict[str, Any]:
    rows = await store.search_nodes(name, limit=3)
    if not rows:
        return {"query": name, "found": False, "nodes": [], "edges": []}

    seed = rows[0]
    visited: Set[str] = {seed.id}
    edge_set: Set[tuple] = set()
    frontier: deque[str] = deque([seed.id])

    edge_types_iter = edge_types or ["CALLS", "IMPORTS", "INHERITS", "USES"]
    directions = ("in", "out") if direction == "both" else (direction,)

    nodes_collected = [
        {"id": seed.id, "name": seed.name, "type": seed.type, "file_path": seed.file_path}
    ]

    for _ in range(depth):
        next_frontier: List[str] = []
        while frontier:
            nid = frontier.popleft()
            for d in directions:
                for et in edge_types_iter:
                    nbrs = await store.neighbors(nid, direction=d, edge_type=et)
                    for nb in nbrs:
                        edge_key = (
                            (nid, nb.id, et) if d == "out" else (nb.id, nid, et)
                        )
                        edge_set.add(edge_key)
                        if nb.id not in visited:
                            visited.add(nb.id)
                            next_frontier.append(nb.id)
                            nodes_collected.append({
                                "id": nb.id, "name": nb.name,
                                "type": nb.type, "file_path": nb.file_path,
                            })
        frontier = deque(next_frontier)
        if not frontier:
            break

    return {
        "query": name, "found": True, "seed": seed.name, "depth": depth,
        "node_count": len(nodes_collected),
        "edge_count": len(edge_set),
        "nodes": nodes_collected,
        "edges": [{"src": s, "tgt": t, "type": ty} for s, t, ty in edge_set],
    }
