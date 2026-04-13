from __future__ import annotations
import hashlib
import logging
from pathlib import Path
from typing import Dict, Optional, Set

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

def compute_sha256(file_path: str | Path) -> str:
    """Compute SHA-256 of a file. Returns empty string on error."""
    try:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError as exc:
        logger.warning("Cannot hash %s: %s", file_path, exc)
        return ""

class HashStore:
    """CRUD for the file_hashes table."""

    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    # ── Read ──────────────────────────────────────────────────────────────────
    async def get_hash(self, path: str) -> Optional[str]:
        row = await self._db.execute(
            text("SELECT sha256 FROM file_hashes WHERE path = :p LIMIT 1"),
            {"p": path},
        )
        result = row.fetchone()
        return result[0] if result else None

    async def get_all_hashes(self) -> Dict[str, str]:
        """Return {path: sha256} for every indexed file."""
        rows = await self._db.execute(
            text("SELECT path, sha256 FROM file_hashes")
        )
        return {row[0]: row[1] for row in rows.fetchall()}

    # ── Write ─────────────────────────────────────────────────────────────────
    async def upsert(
        self,
        path: str,
        sha256: str,
        file_size: int = 0,
        language: str | None = None,
    ) -> None:
        await self._db.execute(
            text(
                """
                INSERT INTO file_hashes (path, sha256, file_size, language)
                VALUES (:path, :sha256, :file_size, :lang)
                ON DUPLICATE KEY UPDATE
                    sha256      = VALUES(sha256),
                    file_size   = VALUES(file_size),
                    language    = VALUES(language),
                    analyzed_at = CURRENT_TIMESTAMP
                """
            ),
            {"path": path, "sha256": sha256, "file_size": file_size, "lang": language},
        )

    async def delete(self, path: str) -> None:
        await self._db.execute(
            text("DELETE FROM file_hashes WHERE path = :p"),
            {"p": path},
        )

    # ── Diff helper ───────────────────────────────────────────────────────────
    async def compute_dirty_set(
        self, current_files: Dict[str, str]
    ) -> Set[str]:
        """
        Compare current on-disk hashes against the registry.
        Returns paths that are new or modified.
        """
        stored = await self.get_all_hashes()
        dirty: Set[str] = set()

        for path, sha in current_files.items():
            if sha and stored.get(path) != sha:
                dirty.add(path)

        return dirty
