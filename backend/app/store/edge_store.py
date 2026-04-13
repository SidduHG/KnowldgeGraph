from __future__ import annotations
import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

def edge_id(source_id: str, target_id: str, edge_type: str) -> str:
    raw = f"{source_id}->{target_id}::{edge_type}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]

@dataclass
class EdgeRecord:
    source_id: str
    target_id: str
    type: str   # DEFINES | IMPORTS | CALLS | INHERITS | CONTAINS | USES | EXPORTS
    file_path: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return edge_id(self.source_id, self.target_id, self.type)

class EdgeStore:
    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def upsert(self, edge: EdgeRecord) -> None:
        await self._db.execute(
            text(
                """
                INSERT INTO edges (id, source_id, target_id, type, metadata, file_path)
                VALUES (:id, :src, :tgt, :type, :meta, :fp)
                ON DUPLICATE KEY UPDATE
                    metadata  = VALUES(metadata),
                    file_path = VALUES(file_path)
                """
            ),
            {
                "id": edge.id,
                "src": edge.source_id,
                "tgt": edge.target_id,
                "type": edge.type,
                "meta": json.dumps(edge.metadata),
                "fp": edge.file_path,
            },
        )

    async def upsert_many(self, edges: List[EdgeRecord]) -> int:
        for edge in edges:
            await self.upsert(edge)
        return len(edges)

    async def delete_by_file(self, file_path: str) -> int:
        result = await self._db.execute(
            text("DELETE FROM edges WHERE file_path = :fp"),
            {"fp": file_path},
        )
        return result.rowcount

    async def get_stats(self) -> dict:
        rows = await self._db.execute(
            text("SELECT type, COUNT(*) FROM edges GROUP BY type")
        )
        return dict(rows.fetchall())
