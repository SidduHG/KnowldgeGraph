from __future__ import annotations
import logging
from typing import List, Set

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

class DepStore:
    """CRUD for the file_deps table (import relationships)."""

    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    # ── Read ──────────────────────────────────────────────────────────────────
    async def get_importers(self, importee: str) -> List[str]:
        """All files that import `importee`."""
        rows = await self._db.execute(
            text("SELECT importer FROM file_deps WHERE importee = :i"),
            {"i": importee},
        )
        return [r[0] for r in rows.fetchall()]

    async def get_importees(self, importer: str) -> List[str]:
        """All files that `importer` imports."""
        rows = await self._db.execute(
            text("SELECT importee FROM file_deps WHERE importer = :i"),
            {"i": importer},
        )
        return [r[0] for r in rows.fetchall()]

    # ── Write ─────────────────────────────────────────────────────────────────
    async def set_deps(self, importer: str, importees: List[str]) -> None:
        """Replace all deps for `importer` with the new set."""
        await self._db.execute(
            text("DELETE FROM file_deps WHERE importer = :i"),
            {"i": importer},
        )
        if importees:
            await self._db.execute(
                text(
                    "INSERT IGNORE INTO file_deps (importer, importee) "
                    "VALUES " + ",".join(["(:imp, :ee)"] * len(importees))
                ),
                {f"imp": importer, **{f"ee_{k}": v for k, v in enumerate(importees)}},
            )
            # Use executemany for clarity
            await self._db.execute(
                text("DELETE FROM file_deps WHERE importer = :i"),
                {"i": importer},
            )
            for ee in importees:
                await self._db.execute(
                    text(
                        "INSERT IGNORE INTO file_deps (importer, importee) VALUES (:imp, :ee)"
                    ),
                    {"imp": importer, "ee": ee},
                )

    async def delete_file(self, path: str) -> None:
        """Remove all deps where this path is either importer or importee."""
        await self._db.execute(
            text("DELETE FROM file_deps WHERE importer = :p OR importee = :p"),
            {"p": path},
        )

    # ── Propagation ───────────────────────────────────────────────────────────
    async def expand_dirty_set(self, dirty: Set[str]) -> Set[str]:
        """
        For every file in dirty, add its direct importers.
        One hop only — avoids cascading the whole graph.
        """
        extra: Set[str] = set()
        for path in list(dirty):
            importers = await self.get_importers(path)
            extra.update(importers)
        return dirty | extra
