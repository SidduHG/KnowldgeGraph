"""File-centric tools: file map, full context, related-files."""
from __future__ import annotations

from typing import Any, Dict, List

from ckg.store.base import GraphStore


async def get_file_map(store: GraphStore, file_path: str) -> Dict[str, Any]:
    nodes = await store.get_nodes_by_file(file_path)
    if not nodes:
        return {"query": file_path, "file_path": file_path, "found": False, "symbols": []}

    out: List[Dict[str, Any]] = []
    for n in nodes:
        callers = await store.neighbors(n.id, direction="in", edge_type="CALLS")
        callees = await store.neighbors(n.id, direction="out", edge_type="CALLS")
        out.append({
            "type": n.type, "name": n.name,
            "start_line": n.start_line, "end_line": n.end_line,
            "signature": n.signature, "docstring": n.docstring,
            "callers": len(callers), "callees": len(callees),
        })
    return {
        "query": file_path,
        "file_path": file_path,
        "found": True,
        "symbol_count": len(out),
        "symbols": out,
    }


async def get_context(store: GraphStore, file_path: str) -> Dict[str, Any]:
    """Aggregate context — symbols + imports + outside callers / callees in one shot."""
    nodes = await store.get_nodes_by_file(file_path)
    if not nodes:
        return {"query": file_path, "file_path": file_path, "found": False}

    imports = await store.get_importees(file_path)

    incoming: List[Dict[str, Any]] = []
    outgoing: List[Dict[str, Any]] = []
    for n in nodes:
        for c in await store.neighbors(n.id, direction="in", edge_type="CALLS"):
            if c.file_path != file_path:
                incoming.append({
                    "from_name": c.name, "from_type": c.type,
                    "from_file": c.file_path, "from_line": c.start_line,
                    "edge_type": "CALLS", "target_name": n.name,
                })
        for c in await store.neighbors(n.id, direction="out", edge_type="CALLS"):
            if c.file_path != file_path:
                outgoing.append({
                    "source_name": n.name, "edge_type": "CALLS",
                    "to_name": c.name, "to_type": c.type,
                    "to_file": c.file_path, "to_line": c.start_line,
                })

    return {
        "query": file_path, "file_path": file_path, "found": True,
        "symbol_count": len(nodes),
        "symbols": [
            {
                "type": n.type, "name": n.name,
                "lines": f"{n.start_line}-{n.end_line}",
                "signature": n.signature, "docstring": n.docstring,
            }
            for n in nodes
        ],
        "imports": imports,
        "incoming_references": incoming,
        "outgoing_references": outgoing,
    }


async def get_related(store: GraphStore, file_path: str) -> Dict[str, Any]:
    importees = await store.get_importees(file_path)
    importers = await store.get_importers(file_path)

    # 2-hop dependents
    two_hop: set[str] = set()
    for imp in importers:
        two_hop.update(await store.get_importers(imp))
    two_hop.discard(file_path)

    return {
        "file_path": file_path,
        "imports": importees,
        "imports_count": len(importees),
        "imported_by": importers,
        "imported_by_count": len(importers),
        "two_hop_dependents": sorted(two_hop),
    }
