from __future__ import annotations
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.parser.base import ParseResult, ParsedEdge, ParsedNode
from app.parser.registry import registry, EXT_MAP
from app.store.dep_store import DepStore
from app.store.edge_store import EdgeRecord, EdgeStore
from app.store.hash_store import HashStore, compute_sha256
from app.store.node_store import NodeRecord, NodeStore, node_id

logger = logging.getLogger(__name__)


def _resolve_import(
    importer_path: str, raw_import: str, repo_root: str
) -> Optional[str]:
    """
    Best-effort resolution of an import string to an absolute path.
    Returns None if resolution fails.
    """
    imp = Path(importer_path)
    repo = Path(repo_root)

    # Relative import (starts with . or /)
    if raw_import.startswith("."):
        candidate = (imp.parent / raw_import.replace(".", "/")).resolve()
        for ext in EXT_MAP:
            full = candidate.with_suffix(ext)
            if full.exists():
                return str(full)
        # Could be a directory with index
        for ext in EXT_MAP:
            full = candidate / f"index{ext}"
            if full.exists():
                return str(full)
        return None

    # Absolute import — try relative to repo root
    parts = raw_import.replace(".", "/")
    candidate = (repo / parts).resolve()
    for ext in EXT_MAP:
        full = candidate.with_suffix(ext)
        if full.exists():
            return str(full)
    return None


class GraphBuilder:
    """
    Converts ParseResult objects into graph nodes and edges,
    then writes them to MySQL via the store layer.
    """

    def __init__(
        self,
        session: AsyncSession,
        repo_path: str,
    ) -> None:
        self._session = session
        self._repo_path = repo_path
        self._nodes = NodeStore(session)
        self._edges = EdgeStore(session)
        self._hashes = HashStore(session)
        self._deps = DepStore(session)

        # Cross-file resolution caches (populated lazily on first use)
        self._qname_index: Optional[Dict[str, str]] = None     # qualified_name → id
        self._name_index: Optional[Dict[str, List[str]]] = None  # name → [ids]

    async def _ensure_indexes(self) -> None:
        """Load qname/name → id indexes from DB once per builder instance."""
        if self._qname_index is not None:
            return
        r = await self._session.execute(
            text("SELECT id, name, qualified_name FROM nodes")
        )
        qname_map: Dict[str, str] = {}
        name_map: Dict[str, List[str]] = {}
        for row in r.fetchall():
            nid, name, qn = row[0], row[1], row[2]
            if qn:
                # Shorter qname wins a collision (closer match usually better)
                prev = qname_map.get(qn)
                if prev is None:
                    qname_map[qn] = nid
            name_map.setdefault(name, []).append(nid)
        self._qname_index = qname_map
        self._name_index = name_map

    def _register_new_nodes(self, node_records: List[NodeRecord]) -> None:
        """Keep the in-memory indexes up-to-date after upserting a file."""
        if self._qname_index is None or self._name_index is None:
            return
        for n in node_records:
            if n.qualified_name:
                self._qname_index[n.qualified_name] = n.id
            ids = self._name_index.setdefault(n.name, [])
            if n.id not in ids:
                ids.append(n.id)

    async def build_file(
        self,
        file_path: str,
        sha256: str,
        language: str,
    ) -> Dict[str, int]:
        """
        Parse one file and upsert its nodes + edges.
        Returns stats dict.
        """
        stats = {"nodes": 0, "edges": 0}

        # 1. Delete stale data for this file
        await self._nodes.delete_by_file(file_path)
        await self._edges.delete_by_file(file_path)
        await self._deps.delete_file(file_path)

        # 2. Parse
        result: Optional[ParseResult] = registry.parse_file(file_path)
        if result is None or not result.ok:
            logger.warning("Parse failed for %s: %s",
                           file_path, result.error if result else "no parser")
            return stats

        # 3. Resolve imports → dep index
        resolved_imports: List[str] = []
        for raw in result.import_paths:
            resolved = _resolve_import(file_path, raw, self._repo_path)
            if resolved:
                resolved_imports.append(resolved)
        await self._deps.set_deps(file_path, resolved_imports)

        # 4. Build a qname → node_id map for edge resolution
        qname_to_id: Dict[str, str] = {}
        node_records: List[NodeRecord] = []

        for pn in result.nodes:
            nid = node_id(pn.file_path, pn.qualified_name, pn.type)
            qname_to_id[pn.qualified_name] = nid
            node_records.append(
                NodeRecord(
                    id=nid,
                    type=pn.type,
                    name=pn.name,
                    qualified_name=pn.qualified_name,
                    file_path=pn.file_path,
                    start_line=pn.start_line,
                    end_line=pn.end_line,
                    signature=pn.signature,
                    docstring=pn.docstring,
                    source_snippet=pn.source_snippet,
                    language=pn.language,
                )
            )

        stats["nodes"] = await self._nodes.upsert_many(node_records)

        # Make newly-upserted nodes available to subsequent cross-file lookups
        await self._ensure_indexes()
        self._register_new_nodes(node_records)

        # 5. Upsert edges — WITH cross-file resolution
        edge_records: List[EdgeRecord] = []
        for pe in result.edges:
            src_id = qname_to_id.get(pe.source_qualified)
            tgt_id = qname_to_id.get(pe.target_qualified)

            # For FILE-level DEFINES, source is the file node
            if src_id is None:
                src_id = qname_to_id.get(pe.source_qualified)

            # ── Cross-file edge resolution ──
            if tgt_id is None and pe.type in ("CALLS", "INHERITS", "IMPORTS"):
                # Try to find the target by name in DB (cross-file lookup)
                tgt_id = await self._resolve_cross_file_target(
                    pe.target_qualified, pe.type
                )

            if src_id is None or tgt_id is None:
                continue

            edge_records.append(
                EdgeRecord(
                    source_id=src_id,
                    target_id=tgt_id,
                    type=pe.type,
                    file_path=pe.file_path,
                    metadata=pe.metadata,
                )
            )

        stats["edges"] = await self._edges.upsert_many(edge_records)

        # 6. Update hash registry
        try:
            size = Path(file_path).stat().st_size
        except OSError:
            size = 0
        await self._hashes.upsert(file_path, sha256, size, language)

        return stats

    async def _resolve_cross_file_target(
        self, target_qualified: str, edge_type: str
    ) -> Optional[str]:
        """
        Resolve a cross-file reference to an existing node ID.
        Handles patterns like:
          - "module.ClassName" → look up by qualified_name suffix
          - "ClassName"        → look up by name
          - "self.method"      → strip self. prefix
          - "obj.method"       → use the short name, verify by suffix when possible

        Uses the in-memory qname/name indexes built once per builder instance,
        so this is O(1) per call after the first.
        """
        await self._ensure_indexes()
        assert self._qname_index is not None and self._name_index is not None

        # Clean up common prefixes
        clean = target_qualified
        if clean.startswith("self."):
            clean = clean[5:]
        elif clean.startswith("cls."):
            clean = clean[4:]

        # 1. Exact qualified-name hit
        hit = self._qname_index.get(clean)
        if hit:
            return hit

        # 2. Suffix match on qualified_name — walk the cache (usually tiny
        # relative to the gain of not issuing a SQL round-trip per edge).
        # Only attempted for dotted references.
        if "." in clean:
            suffix = "." + clean if not clean.startswith(".") else clean
            # Prefer the shortest qname that ends with the suffix
            best: Optional[str] = None
            best_len = 10**9
            for qn, nid in self._qname_index.items():
                if qn.endswith(suffix) and len(qn) < best_len:
                    best = nid
                    best_len = len(qn)
            if best:
                return best
            short_name = clean.rsplit(".", 1)[-1]
        else:
            short_name = clean

        # 3. Fall back to bare-name match.
        # If there is exactly one symbol with this name, it's unambiguous.
        # If many, we skip — a wrong CALLS edge is worse than a missing one.
        ids = self._name_index.get(short_name, [])
        if len(ids) == 1:
            return ids[0]

        return None

    async def build_dirty_set(
        self,
        dirty: Set[str],
        current_hashes: Dict[str, str],
        language_map: Dict[str, str],
    ) -> Dict[str, int]:
        """
        Process all files in the dirty set.
        Returns aggregate stats.
        """
        total = {"nodes": 0, "edges": 0, "files": 0, "errors": 0}
        for fp in dirty:
            sha = current_hashes.get(fp, "")
            lang = language_map.get(fp, "unknown")
            try:
                stats = await self.build_file(fp, sha, lang)
                total["nodes"] += stats["nodes"]
                total["edges"] += stats["edges"]
                total["files"] += 1
                await self._session.commit()
            except Exception as exc:
                logger.error("Error building %s: %s", fp, exc)
                await self._session.rollback()
                total["errors"] += 1

        return total
