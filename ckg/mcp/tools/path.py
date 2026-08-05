"""find_path — shortest path between two symbols across CALLS/IMPORTS edges.

Useful for ``how does function A reach function B?`` style questions.
Implementation: BFS, capped at ``max_hops``.
"""
from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Optional

from ckg.store.base import GraphStore


async def find_path(
    store: GraphStore, source: str, target: str, *, max_hops: int = 6
) -> Dict[str, Any]:
    src_rows = await store.search_nodes(source, limit=1)
    tgt_rows = await store.search_nodes(target, limit=1)
    if not src_rows or not tgt_rows:
        return {"found": False, "source": source, "target": target}

    src_id = src_rows[0].id
    tgt_id = tgt_rows[0].id
    if src_id == tgt_id:
        return {
            "found": True, "hops": 0,
            "path": [{"name": src_rows[0].name, "id": src_id}],
        }

    parent: Dict[str, Optional[str]] = {src_id: None}
    queue: deque[str] = deque([src_id])
    hops = 0
    found = False

    while queue and hops < max_hops:
        layer = list(queue)
        queue.clear()
        hops += 1
        for nid in layer:
            for et in ("CALLS", "IMPORTS", "INHERITS"):
                neighbours = await store.neighbors(nid, direction="out", edge_type=et)
                for nb in neighbours:
                    if nb.id in parent:
                        continue
                    parent[nb.id] = nid
                    if nb.id == tgt_id:
                        found = True
                        break
                    queue.append(nb.id)
                if found:
                    break
            if found:
                break
        if found:
            break

    if not found:
        return {"found": False, "source": source, "target": target, "hops_searched": hops}

    chain: List[str] = []
    nid: Optional[str] = tgt_id
    while nid is not None:
        chain.append(nid)
        nid = parent[nid]
    chain.reverse()

    nodes_path = []
    for nid in chain:
        node = await store.get_node(nid)
        if node:
            nodes_path.append({
                "id": nid, "name": node.name,
                "qualified_name": node.qualified_name,
                "file_path": node.file_path, "type": node.type,
            })
    return {
        "found": True, "source": source, "target": target,
        "hops": len(chain) - 1, "path": nodes_path,
    }
