"""SQLite backend — zero-setup, single-file, perfect for solo devs.

This is the default backend in v3. ``CKG_STORE_BACKEND=mysql`` switches back
to the original MySQL implementation for users who already have the docker
stack running.

Implementation notes:
  * Uses ``aiosqlite`` for async I/O.
  * Schema lives inline (one ``init`` call); no migration tooling needed.
  * Foreign keys are enabled per-connection.
  * The same dataclasses (``NodeRecord``, ``EdgeRecord``, ...) work across
    backends — the row mapping happens here.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from ckg.core.errors import StoreError
from ckg.core.ids import edge_id
from ckg.observability import get_logger
from ckg.store.base import EdgeRecord, FileHashRecord, NodeRecord

logger = get_logger(__name__)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id              TEXT PRIMARY KEY,
    type            TEXT NOT NULL,
    name            TEXT NOT NULL,
    qualified_name  TEXT,
    file_path       TEXT NOT NULL,
    start_line      INTEGER,
    end_line        INTEGER,
    signature       TEXT,
    docstring       TEXT,
    source_snippet  TEXT,
    language        TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_nodes_name      ON nodes(name);
CREATE INDEX IF NOT EXISTS idx_nodes_qname     ON nodes(qualified_name);
CREATE INDEX IF NOT EXISTS idx_nodes_file_path ON nodes(file_path);
CREATE INDEX IF NOT EXISTS idx_nodes_type      ON nodes(type);

CREATE TABLE IF NOT EXISTS edges (
    id          TEXT PRIMARY KEY,
    source_id   TEXT NOT NULL,
    target_id   TEXT NOT NULL,
    type        TEXT NOT NULL,
    metadata    TEXT,
    file_path   TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
CREATE INDEX IF NOT EXISTS idx_edges_type   ON edges(type);
CREATE INDEX IF NOT EXISTS idx_edges_file   ON edges(file_path);

CREATE TABLE IF NOT EXISTS file_hashes (
    path        TEXT PRIMARY KEY,
    sha256      TEXT NOT NULL,
    file_size   INTEGER DEFAULT 0,
    language    TEXT,
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS file_deps (
    importer TEXT NOT NULL,
    importee TEXT NOT NULL,
    PRIMARY KEY (importer, importee)
);
CREATE INDEX IF NOT EXISTS idx_deps_importee ON file_deps(importee);

CREATE TABLE IF NOT EXISTS index_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_type        TEXT NOT NULL,
    repo_path       TEXT,
    files_scanned   INTEGER DEFAULT 0,
    files_indexed   INTEGER DEFAULT 0,
    files_skipped   INTEGER DEFAULT 0,
    nodes_created   INTEGER DEFAULT 0,
    edges_created   INTEGER DEFAULT 0,
    duration_ms     INTEGER DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'RUNNING',
    error_message   TEXT,
    started_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at    TIMESTAMP
);
"""

_NODE_COLS = (
    "id, type, name, qualified_name, file_path, start_line, end_line, "
    "signature, docstring, source_snippet, language"
)


def _row_to_node(row: Any) -> NodeRecord:
    return NodeRecord(
        id=row[0], type=row[1], name=row[2],
        qualified_name=row[3] or "",
        file_path=row[4],
        start_line=row[5], end_line=row[6],
        signature=row[7], docstring=row[8],
        source_snippet=row[9], language=row[10],
    )


def _row_to_edge(row: Any) -> EdgeRecord:
    metadata: Dict[str, Any] = {}
    if row[4]:
        try:
            metadata = json.loads(row[4])
        except (TypeError, ValueError):
            metadata = {}
    return EdgeRecord(
        source_id=row[1], target_id=row[2],
        type=row[3], metadata=metadata, file_path=row[5],
    )


class SQLiteGraphStore:
    """``GraphStore`` over aiosqlite. Stores everything in one file."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._db: Any = None  # aiosqlite.Connection

    # ── Lifecycle ────────────────────────────────────────────────────────────
    async def init(self) -> None:
        try:
            import aiosqlite
        except ImportError as exc:  # pragma: no cover
            raise StoreError(
                "aiosqlite is required for the SQLite backend — `pip install aiosqlite`"
            ) from exc

        Path(os.path.dirname(self._path) or ".").mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._path)
        await self._db.execute("PRAGMA foreign_keys = ON")
        await self._db.execute("PRAGMA journal_mode = WAL")
        await self._db.executescript(_SCHEMA)
        await self._db.commit()
        logger.info("SQLite store initialized at %s", self._path)

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def clear_all(self) -> None:
        await self._db.execute("DELETE FROM edges")
        await self._db.execute("DELETE FROM nodes")
        await self._db.execute("DELETE FROM file_hashes")
        await self._db.execute("DELETE FROM file_deps")
        await self._db.execute("DELETE FROM index_runs")
        await self._db.commit()

    # ── Nodes ────────────────────────────────────────────────────────────────
    async def upsert_nodes(self, nodes: List[NodeRecord]) -> int:
        if not nodes:
            return 0
        sql = (
            f"INSERT INTO nodes ({_NODE_COLS}) VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "type=excluded.type, name=excluded.name, "
            "qualified_name=excluded.qualified_name, "
            "file_path=excluded.file_path, "
            "start_line=excluded.start_line, end_line=excluded.end_line, "
            "signature=excluded.signature, docstring=excluded.docstring, "
            "source_snippet=excluded.source_snippet, language=excluded.language, "
            "updated_at=CURRENT_TIMESTAMP"
        )
        rows = [
            (
                n.id, n.type, n.name, n.qualified_name, n.file_path,
                n.start_line, n.end_line, n.signature, n.docstring,
                (n.source_snippet or "")[:2000], n.language,
            )
            for n in nodes
        ]
        await self._db.executemany(sql, rows)
        await self._db.commit()
        return len(rows)

    async def delete_nodes_by_file(self, file_path: str) -> int:
        cur = await self._db.execute("DELETE FROM nodes WHERE file_path = ?", (file_path,))
        await self._db.commit()
        return cur.rowcount

    async def list_nodes(
        self,
        *,
        type: Optional[str] = None,
        language: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[NodeRecord]:
        wheres: List[str] = []
        params: List[Any] = []
        if type:
            wheres.append("type = ?"); params.append(type.upper())
        if language:
            wheres.append("language = ?"); params.append(language)
        where_sql = ("WHERE " + " AND ".join(wheres)) if wheres else ""
        params.extend([limit, offset])
        sql = (
            f"SELECT {_NODE_COLS} FROM nodes {where_sql} "
            "ORDER BY file_path, start_line LIMIT ? OFFSET ?"
        )
        cur = await self._db.execute(sql, params)
        rows = await cur.fetchall()
        return [_row_to_node(r) for r in rows]

    async def get_node(self, node_id: str) -> Optional[NodeRecord]:
        cur = await self._db.execute(
            f"SELECT {_NODE_COLS} FROM nodes WHERE id = ?", (node_id,)
        )
        row = await cur.fetchone()
        return _row_to_node(row) if row else None

    async def get_nodes_by_file(self, file_path: str) -> List[NodeRecord]:
        cur = await self._db.execute(
            f"SELECT {_NODE_COLS} FROM nodes WHERE file_path = ? ORDER BY start_line",
            (file_path,),
        )
        rows = await cur.fetchall()
        return [_row_to_node(r) for r in rows]

    async def search_nodes(self, query: str, limit: int = 20) -> List[NodeRecord]:
        like = f"%{query}%"
        cur = await self._db.execute(
            f"SELECT {_NODE_COLS} FROM nodes "
            "WHERE name LIKE ? OR qualified_name LIKE ? "
            "ORDER BY length(name) LIMIT ?",
            (like, like, limit),
        )
        rows = await cur.fetchall()
        return [_row_to_node(r) for r in rows]

    async def get_qname_index(self) -> Dict[str, str]:
        cur = await self._db.execute("SELECT id, qualified_name FROM nodes")
        rows = await cur.fetchall()
        out: Dict[str, str] = {}
        for nid, qn in rows:
            if qn and qn not in out:
                out[qn] = nid
        return out

    async def get_name_index(self) -> Dict[str, List[str]]:
        cur = await self._db.execute("SELECT id, name FROM nodes")
        rows = await cur.fetchall()
        out: Dict[str, List[str]] = {}
        for nid, name in rows:
            out.setdefault(name, []).append(nid)
        return out

    # ── Edges ────────────────────────────────────────────────────────────────
    async def upsert_edges(self, edges: List[EdgeRecord]) -> int:
        if not edges:
            return 0
        sql = (
            "INSERT INTO edges (id, source_id, target_id, type, metadata, file_path) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "metadata=excluded.metadata, file_path=excluded.file_path"
        )
        rows = [
            (
                edge_id(e.source_id, e.target_id, e.type),
                e.source_id, e.target_id, e.type,
                json.dumps(e.metadata or {}), e.file_path,
            )
            for e in edges
        ]
        await self._db.executemany(sql, rows)
        await self._db.commit()
        return len(rows)

    async def delete_edges_by_file(self, file_path: str) -> int:
        cur = await self._db.execute("DELETE FROM edges WHERE file_path = ?", (file_path,))
        await self._db.commit()
        return cur.rowcount

    async def list_edges(
        self,
        *,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        type: Optional[str] = None,
        limit: int = 100,
    ) -> List[EdgeRecord]:
        wheres: List[str] = []
        params: List[Any] = []
        if source_id:
            wheres.append("source_id = ?"); params.append(source_id)
        if target_id:
            wheres.append("target_id = ?"); params.append(target_id)
        if type:
            wheres.append("type = ?"); params.append(type.upper())
        where_sql = ("WHERE " + " AND ".join(wheres)) if wheres else ""
        params.append(limit)
        sql = (
            "SELECT id, source_id, target_id, type, metadata, file_path "
            f"FROM edges {where_sql} LIMIT ?"
        )
        cur = await self._db.execute(sql, params)
        rows = await cur.fetchall()
        return [_row_to_edge(r) for r in rows]

    async def neighbors(
        self,
        node_id: str,
        *,
        direction: str = "out",
        edge_type: Optional[str] = None,
    ) -> List[NodeRecord]:
        if direction == "out":
            join = "n.id = e.target_id"; where = "e.source_id = ?"
        elif direction == "in":
            join = "n.id = e.source_id"; where = "e.target_id = ?"
        else:
            # both
            cur = await self._db.execute(
                f"SELECT {', '.join('n.' + c for c in _NODE_COLS.split(', '))} "
                "FROM nodes n JOIN edges e ON (n.id=e.source_id OR n.id=e.target_id) "
                "WHERE (e.source_id=? OR e.target_id=?)" + (
                    " AND e.type=?" if edge_type else ""
                ),
                ((node_id, node_id, edge_type) if edge_type else (node_id, node_id)),
            )
            rows = await cur.fetchall()
            return [_row_to_node(r) for r in rows]

        sql = (
            f"SELECT {', '.join('n.' + c for c in _NODE_COLS.split(', '))} "
            f"FROM nodes n JOIN edges e ON {join} WHERE {where}"
        )
        params: List[Any] = [node_id]
        if edge_type:
            sql += " AND e.type = ?"
            params.append(edge_type)
        cur = await self._db.execute(sql, params)
        rows = await cur.fetchall()
        return [_row_to_node(r) for r in rows]

    # ── File hashes ──────────────────────────────────────────────────────────
    async def get_hash(self, path: str) -> Optional[str]:
        cur = await self._db.execute(
            "SELECT sha256 FROM file_hashes WHERE path = ?", (path,)
        )
        row = await cur.fetchone()
        return row[0] if row else None

    async def get_all_hashes(self) -> Dict[str, str]:
        cur = await self._db.execute("SELECT path, sha256 FROM file_hashes")
        rows = await cur.fetchall()
        return dict(rows)

    async def upsert_hash(self, record: FileHashRecord) -> None:
        await self._db.execute(
            "INSERT INTO file_hashes (path, sha256, file_size, language) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(path) DO UPDATE SET "
            "sha256=excluded.sha256, file_size=excluded.file_size, "
            "language=excluded.language, analyzed_at=CURRENT_TIMESTAMP",
            (record.path, record.sha256, record.size, record.language),
        )
        await self._db.commit()

    async def delete_hash(self, path: str) -> None:
        await self._db.execute("DELETE FROM file_hashes WHERE path = ?", (path,))
        await self._db.commit()

    # ── File deps ────────────────────────────────────────────────────────────
    async def set_deps(self, importer: str, importees: List[str]) -> None:
        await self._db.execute("DELETE FROM file_deps WHERE importer = ?", (importer,))
        if importees:
            await self._db.executemany(
                "INSERT OR IGNORE INTO file_deps (importer, importee) VALUES (?, ?)",
                [(importer, ee) for ee in importees],
            )
        await self._db.commit()

    async def get_importers(self, importee: str) -> List[str]:
        cur = await self._db.execute(
            "SELECT importer FROM file_deps WHERE importee = ?", (importee,)
        )
        rows = await cur.fetchall()
        return [r[0] for r in rows]

    async def get_importees(self, importer: str) -> List[str]:
        cur = await self._db.execute(
            "SELECT importee FROM file_deps WHERE importer = ?", (importer,)
        )
        rows = await cur.fetchall()
        return [r[0] for r in rows]

    async def delete_file_deps(self, path: str) -> None:
        await self._db.execute(
            "DELETE FROM file_deps WHERE importer = ? OR importee = ?", (path, path)
        )
        await self._db.commit()

    async def expand_dirty_set(self, dirty: Set[str]) -> Set[str]:
        if not dirty:
            return dirty
        # One-hop reverse deps
        placeholders = ",".join("?" * len(dirty))
        cur = await self._db.execute(
            f"SELECT importer FROM file_deps WHERE importee IN ({placeholders})",
            tuple(dirty),
        )
        extra = {r[0] for r in await cur.fetchall()}
        return dirty | extra

    # ── Stats ────────────────────────────────────────────────────────────────
    async def stats(self) -> Dict[str, Any]:
        cur = await self._db.execute("SELECT COUNT(*) FROM nodes")
        total_nodes = (await cur.fetchone())[0]
        cur = await self._db.execute("SELECT COUNT(*) FROM edges")
        total_edges = (await cur.fetchone())[0]
        cur = await self._db.execute("SELECT COUNT(*) FROM file_hashes")
        total_files = (await cur.fetchone())[0]

        cur = await self._db.execute("SELECT type, COUNT(*) FROM nodes GROUP BY type")
        node_types = dict(await cur.fetchall())
        cur = await self._db.execute("SELECT type, COUNT(*) FROM edges GROUP BY type")
        edge_types = dict(await cur.fetchall())
        cur = await self._db.execute(
            "SELECT language, COUNT(*) FROM file_hashes "
            "WHERE language IS NOT NULL GROUP BY language ORDER BY 2 DESC"
        )
        languages = dict(await cur.fetchall())

        cur = await self._db.execute(
            "SELECT file_path, COUNT(*) AS c FROM nodes "
            "GROUP BY file_path ORDER BY c DESC LIMIT 10"
        )
        hotspots = [{"file": r[0], "symbols": r[1]} for r in await cur.fetchall()]

        return {
            "total_files": total_files,
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "node_types": node_types,
            "edge_types": edge_types,
            "languages": list(languages.keys()),
            "hotspot_files": hotspots,
        }
