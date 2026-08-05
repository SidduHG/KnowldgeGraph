"""rank_symbols — PageRank top-k. Helps agents orient on a new repo."""
from __future__ import annotations

from typing import Any, Dict

from ckg.ranking.pagerank import compute_pagerank
from ckg.store.base import GraphStore


async def rank_symbols(store: GraphStore, k: int = 20) -> Dict[str, Any]:
    rank = await compute_pagerank(store)
    if not rank:
        return {"found": False, "results": []}

    top_ids = sorted(rank.items(), key=lambda x: -x[1])[:k]
    out = []
    for nid, score in top_ids:
        n = await store.get_node(nid)
        if not n:
            continue
        out.append({
            "score": round(score, 6),
            "name": n.name, "qualified_name": n.qualified_name,
            "type": n.type, "file_path": n.file_path,
            "start_line": n.start_line,
        })

    return {"found": True, "k": k, "count": len(out), "results": out}
