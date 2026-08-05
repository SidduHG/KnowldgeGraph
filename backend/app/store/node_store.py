from __future__ import annotations
import hashlib
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

def node_id(file_path: str, name: str, node_type: str) -> str:
    """Deterministic node ID from file + name + type."""
    raw = f"{file_path}::{name}::{node_type}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]

@dataclass
class NodeRecord:
    id: str
    type: str               # FILE | CLASS | FUNCTION | METHOD | VARIABLE | TYPE | MODULE
    name: str
    file_path: str
    qualified_name: str = ""
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    signature: Optional[str] = None
    docstring: Optional[str] = None
    source_snippet: Optional[str] = None
    language: Optional[str] = None

class NodeStore:
    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    # ── Write ─────────────────────────────────────────────────────────────────
    async def upsert(self, node: NodeRecord) -> None:
        await self._db.execute(
            text(
                """
                INSERT INTO nodes
                    (id, type, name, qualified_name, file_path,
                     start_line, end_line, signature, docstring, source_snippet, language)
                VALUES
                    (:id, :type, :name, :qn, :fp,
                     :sl, :el, :sig, :doc, :snip, :lang)
                ON DUPLICATE KEY UPDATE
                    type            = VALUES(type),
                    name            = VALUES(name),
                    qualified_name  = VALUES(qualified_name),
                    file_path       = VALUES(file_path),
                    start_line      = VALUES(start_line),
                    end_line        = VALUES(end_line),
                    signature       = VALUES(signature),
                    docstring       = VALUES(docstring),
                    source_snippet  = VALUES(source_snippet),
                    language        = VALUES(language),
                    updated_at      = CURRENT_TIMESTAMP
                """
            ),
            {
                "id": node.id,
                "type": node.type,
                "name": node.name,
                "qn": node.qualified_name,
                "fp": node.file_path,
                "sl": node.start_line,
                "el": node.end_line,
                "sig": node.signature,
                "doc": node.docstring,
                "snip": (node.source_snippet or "")[:2000],
                "lang": node.language,
            },
        )

    async def upsert_many(self, nodes: List[NodeRecord]) -> int:
        for node in nodes:
            await self.upsert(node)
        return len(nodes)

    async def delete_by_file(self, file_path: str) -> int:
        result = await self._db.execute(
            text("DELETE FROM nodes WHERE file_path = :fp"),
            {"fp": file_path},
        )
        return result.rowcount

    # ── Read ──────────────────────────────────────────────────────────────────
    async def get_by_file(self, file_path: str) -> List[dict]:
        rows = await self._db.execute(
            text(
                "SELECT id, type, name, qualified_name, start_line, end_line, "
                "signature, docstring, language "
                "FROM nodes WHERE file_path = :fp ORDER BY start_line"
            ),
            {"fp": file_path},
        )
        keys = ["id","type","name","qualified_name","start_line","end_line",
                "signature","docstring","language"]
        return [dict(zip(keys, row)) for row in rows.fetchall()]

    async def get_stats(self) -> dict:
        rows = await self._db.execute(
            text("SELECT type, COUNT(*) FROM nodes GROUP BY type")
        )
        return dict(rows.fetchall())
