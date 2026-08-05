"""Call graph tools: get_callers, get_callees, and N-hop ``call_graph``.

``call_graph`` is the new addition — gives an agent the full N-hop subtree
of who-calls-what so it can reason about transitive impact in one call.
"""
from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Optional

from ckg.store.base import GraphStore, NodeRecord


async def _resolve(store: GraphStore, name: str) -> Optional[NodeRecord]:
    rows = await store.search_nodes(name, limit=3)
    return rows[0] if rows else None


async def get_callers(store: GraphStore, name: str) -> Dict[str, Any]:
    n = await _resolve(store, name)
    if not n:
        return {"query": name, "found": False, "callers": [], "caller_count": 0}
    callers = await store.neighbors(n.id, direction="in", edge_type="CALLS")
    return {
        "query": name, "found": True, "target": n.name,
        "caller_count": len(callers),
        "callers": [
            {
                "name": c.name, "qualified_name": c.qualified_name,
                "file_path": c.file_path, "start_line": c.start_line,
            }
            for c in callers
        ],
    }


async def get_callees(store: GraphStore, name: str) -> Dict[str, Any]:
    n = await _resolve(store, name)
    if not n:
        return {"query": name, "found": False, "callees": [], "callee_count": 0}
    callees = await store.neighbors(n.id, direction="out", edge_type="CALLS")
    return {
        "query": name, "found": True, "source": n.name,
        "callee_count": len(callees),
        "callees": [
            {
                "name": c.name, "qualified_name": c.qualified_name,
                "file_path": c.file_path, "start_line": c.start_line,
            }
            for c in callees
        ],
    }


async def call_graph(
    store: GraphStore, name: str, *, depth: int = 2, direction: str = "both"
) -> Dict[str, Any]:
    """N-hop caller/callee subtree.

    ``direction``: "in" (callers), "out" (callees), or "both".
    """
    n = await _resolve(store, name)
    if not n:
        return {"query": name, "found": False, "depth": depth, "edges": []}

    visited: set[str] = {n.id}
    layers: List[List[Dict[str, Any]]] = []
    frontier: deque[str] = deque([n.id])

    for hop in range(depth):
        next_frontier: List[str] = []
        layer: List[Dict[str, Any]] = []
        while frontier:
            nid = frontier.popleft()
            for d in (("out", "in") if direction == "both" else (direction,)):
                neighbours = await store.neighbors(nid, direction=d, edge_type="CALLS")
                for nb in neighbours:
                    if nb.id in visited:
                        continue
                    visited.add(nb.id)
                    next_frontier.append(nb.id)
                    layer.append({
                        "from_id": nid, "to_id": nb.id,
                        "name": nb.name, "qualified_name": nb.qualified_name,
                        "file_path": nb.file_path, "start_line": nb.start_line,
                        "direction": d, "hop": hop + 1,
                    })
        layers.append(layer)
        frontier = deque(next_frontier)
        if not frontier:
            break

    edges = [e for layer in layers for e in layer]
    return {
        "query": name, "found": True, "root": n.name,
        "depth": depth, "direction": direction,
        "edge_count": len(edges), "edges": edges,
    }
