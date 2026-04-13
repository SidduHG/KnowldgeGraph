from __future__ import annotations
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

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
                    language=pn.language,
                )
            )

        stats["nodes"] = await self._nodes.upsert_many(node_records)

        # 5. Upsert edges (skip unresolved targets)
        edge_records: List[EdgeRecord] = []
        for pe in result.edges:
            src_id = qname_to_id.get(pe.source_qualified)
            tgt_id = qname_to_id.get(pe.target_qualified)

            # For FILE-level DEFINES, source is the file node
            if src_id is None:
                src_id = qname_to_id.get(pe.source_qualified)
            if src_id is None or tgt_id is None:
                # Cross-file edge — skip for now; Phase 2 handles cross-file resolution
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
