"""PageRank over the knowledge graph.

Why PageRank? When an agent asks "what are the most important symbols in
this repo?", the answer isn't just node degree — it's *whose callers are
themselves heavily called*. Classic PageRank captures that recursively.

Implementation is iterative power-method, ~100 iterations, no NumPy
dependency. Good for graphs up to ~500K nodes.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

from ckg.store.base import GraphStore


async def compute_pagerank(
    store: GraphStore,
    *,
    damping: float = 0.85,
    iterations: int = 50,
    tol: float = 1e-6,
) -> Dict[str, float]:
    """Return ``{node_id: rank}`` over edges of type CALLS / IMPORTS / INHERITS.

    Excludes DEFINES / CONTAINS edges — they describe ownership, not influence.
    """
    edges = await store.list_edges(limit=1_000_000)
    if not edges:
        return {}

    # Adjacency for outbound edges (PageRank flows from src → tgt).
    out: Dict[str, List[str]] = defaultdict(list)
    nodes_set: set[str] = set()
    for e in edges:
        if e.type not in ("CALLS", "IMPORTS", "INHERITS", "USES", "REFERENCES"):
            continue
        out[e.source_id].append(e.target_id)
        nodes_set.add(e.source_id)
        nodes_set.add(e.target_id)

    if not nodes_set:
        return {}

    n = len(nodes_set)
    rank: Dict[str, float] = {nid: 1.0 / n for nid in nodes_set}

    # Precompute reverse edges so each iteration is O(E) not O(V²).
    incoming: Dict[str, List[str]] = defaultdict(list)
    out_degree: Dict[str, int] = {nid: len(out.get(nid, [])) for nid in nodes_set}
    for src, targets in out.items():
        for tgt in targets:
            incoming[tgt].append(src)

    for _ in range(iterations):
        diff = 0.0
        new_rank: Dict[str, float] = {}
        for nid in nodes_set:
            inflow = sum(
                rank[src] / out_degree[src] for src in incoming.get(nid, []) if out_degree[src]
            )
            r = (1 - damping) / n + damping * inflow
            diff += abs(r - rank[nid])
            new_rank[nid] = r
        rank = new_rank
        if diff < tol:
            break

    return rank


async def top_k(store: GraphStore, k: int = 20) -> List[Tuple[str, float]]:
    """Convenience: return the top-k nodes sorted by PageRank."""
    rank = await compute_pagerank(store)
    return sorted(rank.items(), key=lambda x: -x[1])[:k]
