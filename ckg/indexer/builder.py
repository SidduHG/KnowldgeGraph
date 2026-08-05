"""Graph builder — turns ``ParseResult`` objects into upsertable records.

Splits cleanly into:
  1. Local resolution (qname → node id) inside one file.
  2. Cross-file resolution against an in-memory snapshot of the qname/name
     indexes — refreshed lazily.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from ckg.core import ParseResult
from ckg.core.ids import node_id
from ckg.observability import counter, get_logger, histogram
from ckg.parsers.registry import EXT_MAP, parse_file
from ckg.store.base import EdgeRecord, FileHashRecord, GraphStore, NodeRecord

logger = get_logger(__name__)

_BUILD_FILES = counter("ckg_build_files_total", "Files passed through the builder")
_BUILD_TIME = histogram("ckg_build_seconds", "Wall time per build_file call")
_NODES_UPSERTED = counter("ckg_nodes_upserted_total", "Total nodes upserted")
_EDGES_UPSERTED = counter("ckg_edges_upserted_total", "Total edges upserted")


def _resolve_import(importer_path: str, raw: str, repo_root: str) -> Optional[str]:
    """Best-effort: turn an import string into an absolute path."""
    imp = Path(importer_path)
    repo = Path(repo_root)

    if raw.startswith("."):
        candidate = (imp.parent / raw.replace(".", "/")).resolve()
        for ext in EXT_MAP:
            if candidate.with_suffix(ext).exists():
                return str(candidate.with_suffix(ext))
            idx = candidate / f"index{ext}"
            if idx.exists():
                return str(idx)
        return None

    parts = raw.replace(".", "/")
    candidate = (repo / parts).resolve()
    for ext in EXT_MAP:
        if candidate.with_suffix(ext).exists():
            return str(candidate.with_suffix(ext))
    return None


class GraphBuilder:
    """Drives one repo's worth of ``parse → upsert`` work against a ``GraphStore``."""

    def __init__(self, store: GraphStore, repo_path: str) -> None:
        self._store = store
        self._repo = repo_path
        self._qname_index: Optional[Dict[str, str]] = None
        self._name_index: Optional[Dict[str, List[str]]] = None

    async def _ensure_indexes(self) -> None:
        if self._qname_index is None:
            self._qname_index = await self._store.get_qname_index()
        if self._name_index is None:
            self._name_index = await self._store.get_name_index()

    def _register(self, nodes: List[NodeRecord]) -> None:
        if self._qname_index is None or self._name_index is None:
            return
        for n in nodes:
            if n.qualified_name and n.qualified_name not in self._qname_index:
                self._qname_index[n.qualified_name] = n.id
            ids = self._name_index.setdefault(n.name, [])
            if n.id not in ids:
                ids.append(n.id)

    # ── Cross-file lookup ────────────────────────────────────────────────────
    async def _resolve_target(self, target: str) -> Optional[str]:
        await self._ensure_indexes()
        assert self._qname_index is not None and self._name_index is not None

        clean = target
        if clean.startswith("self."):
            clean = clean[5:]
        elif clean.startswith("cls."):
            clean = clean[4:]

        # Exact qualified match
        if clean in self._qname_index:
            return self._qname_index[clean]

        # Suffix match — prefer the shortest qname that ends with ".<clean>"
        if "." in clean:
            suffix = "." + clean
            best: Optional[str] = None
            best_len = 10**9
            for qn, nid in self._qname_index.items():
                if qn.endswith(suffix) and len(qn) < best_len:
                    best, best_len = nid, len(qn)
            if best:
                return best
            short = clean.rsplit(".", 1)[-1]
        else:
            short = clean

        # Bare-name fallback — only if unambiguous.
        ids = self._name_index.get(short, [])
        if len(ids) == 1:
            return ids[0]
        return None

    # ── Main entry ───────────────────────────────────────────────────────────
    async def build_file(self, file_path: str, sha256: str, language: str) -> Dict[str, int]:
        with _BUILD_TIME.time(labels={"lang": language}):
            stats = await self._build_file_inner(file_path, sha256, language)
        _BUILD_FILES.inc(labels={"lang": language})
        return stats

    async def _build_file_inner(
        self, file_path: str, sha256: str, language: str
    ) -> Dict[str, int]:
        # 1. Wipe stale data for this file
        await self._store.delete_nodes_by_file(file_path)
        await self._store.delete_edges_by_file(file_path)
        await self._store.delete_file_deps(file_path)

        # 2. Parse
        result: Optional[ParseResult] = parse_file(file_path)
        if result is None or not result.ok:
            err = result.error if result else "no parser"
            logger.warning("Parse failed: %s — %s", file_path, err)
            return {"nodes": 0, "edges": 0}

        # 3. Resolve imports → file_deps + IMPORTS edges
        resolved: List[str] = []
        for raw in result.import_paths:
            res = _resolve_import(file_path, raw, self._repo)
            if res:
                resolved.append(res)
        await self._store.set_deps(file_path, resolved)

        # 4. Build node records
        qname_to_id: Dict[str, str] = {}
        records: List[NodeRecord] = []
        for pn in result.nodes:
            nid = node_id(pn.file_path, pn.qualified_name, pn.type)
            qname_to_id[pn.qualified_name] = nid
            records.append(
                NodeRecord(
                    id=nid, type=pn.type, name=pn.name,
                    qualified_name=pn.qualified_name, file_path=pn.file_path,
                    start_line=pn.start_line, end_line=pn.end_line,
                    signature=pn.signature, docstring=pn.docstring,
                    source_snippet=pn.source_snippet, language=pn.language,
                )
            )
        n_nodes = await self._store.upsert_nodes(records)
        _NODES_UPSERTED.inc(n_nodes, labels={"lang": language})
        await self._ensure_indexes()
        self._register(records)

        # 5. Build edge records (cross-file resolution where needed)
        edges: List[EdgeRecord] = []
        for pe in result.edges:
            src_id = qname_to_id.get(pe.source_qualified)
            tgt_id = qname_to_id.get(pe.target_qualified)

            if tgt_id is None and pe.type in ("CALLS", "INHERITS", "IMPORTS"):
                tgt_id = await self._resolve_target(pe.target_qualified)

            if src_id is None or tgt_id is None:
                continue

            edges.append(
                EdgeRecord(
                    source_id=src_id, target_id=tgt_id,
                    type=pe.type, file_path=pe.file_path,
                    metadata=pe.metadata or {},
                )
            )
        n_edges = await self._store.upsert_edges(edges)
        _EDGES_UPSERTED.inc(n_edges, labels={"lang": language})

        # 6. Update hash registry
        try:
            size = Path(file_path).stat().st_size
        except OSError:
            size = 0
        await self._store.upsert_hash(
            FileHashRecord(path=file_path, sha256=sha256, size=size, language=language)
        )
        return {"nodes": n_nodes, "edges": n_edges}
