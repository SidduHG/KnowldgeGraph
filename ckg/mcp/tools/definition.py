"""Definition lookups — find by name, full def + call graph, class hierarchy."""
from __future__ import annotations

from typing import Any, Dict, Optional

from ckg.store.base import GraphStore


async def get_function(store: GraphStore, name: str) -> Dict[str, Any]:
    """Return any FUNCTION / CLASS / METHOD whose name matches."""
    rows = await store.search_nodes(name, limit=10)
    rows = [r for r in rows if r.type in ("FUNCTION", "CLASS", "METHOD") or r.name == name]
    return {
        "query": name,
        "found": bool(rows),
        "count": len(rows),
        "results": [_node_dict(r) for r in rows],
    }


async def get_definition(store: GraphStore, name: str) -> Dict[str, Any]:
    """Return the full definition of a symbol — including 1-hop call graph."""
    rows = await store.search_nodes(name, limit=5)
    if not rows:
        return {"query": name, "found": False, "count": 0, "results": []}

    out = []
    for n in rows:
        callers = await store.neighbors(n.id, direction="in", edge_type="CALLS")
        callees = await store.neighbors(n.id, direction="out", edge_type="CALLS")
        d = _node_dict(n)
        d["calls"] = [{"name": c.name, "type": c.type} for c in callees]
        d["called_by"] = [{"name": c.name, "type": c.type} for c in callers]
        out.append(d)

    return {"query": name, "found": True, "count": len(out), "results": out}


async def get_hierarchy(store: GraphStore, class_name: str) -> Dict[str, Any]:
    """Class inheritance tree: parents (INHERITS out), children (INHERITS in), methods (CONTAINS)."""
    rows = await store.search_nodes(class_name, limit=5)
    rows = [r for r in rows if r.type == "CLASS"]
    if not rows:
        return {"query": class_name, "found": False}

    cls = rows[0]
    parents = await store.neighbors(cls.id, direction="out", edge_type="INHERITS")
    children = await store.neighbors(cls.id, direction="in", edge_type="INHERITS")
    methods = await store.neighbors(cls.id, direction="out", edge_type="CONTAINS")

    return {
        "query": class_name,
        "found": True,
        "class_name": cls.name,
        "class_info": _node_dict(cls),
        "parents": [{"name": p.name, "file": p.file_path, "line": p.start_line} for p in parents],
        "children": [{"name": c.name, "file": c.file_path, "line": c.start_line} for c in children],
        "methods": [
            {"name": m.name, "signature": m.signature, "line": m.start_line} for m in methods
        ],
    }


def _node_dict(n: Any) -> Dict[str, Any]:
    return {
        "type": n.type, "name": n.name, "qualified_name": n.qualified_name,
        "file_path": n.file_path, "start_line": n.start_line, "end_line": n.end_line,
        "signature": n.signature, "docstring": n.docstring, "language": n.language,
    }
