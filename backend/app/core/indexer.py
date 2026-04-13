from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, Set

from sqlalchemy import text

from app.config import settings
from app.core.builder import GraphBuilder
from app.core.scanner import RepoScanner
from app.database.connection import db_session
from app.store.dep_store import DepStore
from app.store.hash_store import HashStore
from app.parser.registry import EXT_MAP

logger = logging.getLogger(__name__)


class IndexStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IndexProgress:
    status: IndexStatus = IndexStatus.IDLE
    run_type: str = ""
    repo_path: str = ""
    files_total: int = 0
    files_done: int = 0
    files_skipped: int = 0
    nodes_created: int = 0
    edges_created: int = 0
    errors: int = 0
    started_at: float = 0.0
    completed_at: float = 0.0
    error_message: str = ""

    @property
    def elapsed_ms(self) -> int:
        end = self.completed_at or time.time()
        return int((end - self.started_at) * 1000)

    @property
    def pct(self) -> int:
        if self.files_total == 0:
            return 0
        return int(self.files_done / self.files_total * 100)


class IndexerService:
    """
    Singleton service that manages indexing state and coordinates
    the scanner + dirty-set propagation + graph builder.
    """

    _instance: Optional["IndexerService"] = None

    def __init__(self) -> None:
        self.progress = IndexProgress()
        self._lock = asyncio.Lock()

    @classmethod
    def get(cls) -> "IndexerService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def is_running(self) -> bool:
        return self.progress.status == IndexStatus.RUNNING

    # ── Full index ─────────────────────────────────────────────────────────────
    async def run_full(self, repo_path: str) -> IndexProgress:
        async with self._lock:
            if self.is_running:
                raise RuntimeError("Index already running")
            self.progress = IndexProgress(
                status=IndexStatus.RUNNING,
                run_type="FULL",
                repo_path=repo_path,
                started_at=time.time(),
            )

        run_id = await self._start_run("FULL", repo_path)

        try:
            scanner = RepoScanner(repo_path)
            current_hashes = scanner.scan_with_hashes()
            language_map = {
                fp: EXT_MAP.get(Path(fp).suffix.lower(), "unknown")
                for fp in current_hashes
            }

            # Force re-index everything
            dirty = set(current_hashes.keys())
            self.progress.files_total = len(dirty)

            async with db_session() as session:
                deps = DepStore(session)
                dirty = await deps.expand_dirty_set(dirty)
                builder = GraphBuilder(session, repo_path)
                stats = await builder.build_dirty_set(dirty, current_hashes, language_map)

            self.progress.nodes_created = stats["nodes"]
            self.progress.edges_created = stats["edges"]
            self.progress.files_done = stats["files"]
            self.progress.errors = stats["errors"]
            self.progress.status = IndexStatus.COMPLETED
            self.progress.completed_at = time.time()
            await self._complete_run(run_id, self.progress)

        except Exception as exc:
            logger.error("Full index failed: %s", exc)
            self.progress.status = IndexStatus.FAILED
            self.progress.error_message = str(exc)
            self.progress.completed_at = time.time()
            await self._fail_run(run_id, str(exc))

        return self.progress

    # ── Incremental index (one file) ──────────────────────────────────────────
    async def run_incremental(
        self, file_path: str, repo_path: str, deleted: bool = False
    ) -> IndexProgress:
        async with self._lock:
            if self.is_running:
                # Queue or skip — for now skip
                logger.debug("Skipping incremental index (full in progress)")
                return self.progress
            self.progress = IndexProgress(
                status=IndexStatus.RUNNING,
                run_type="INCREMENTAL",
                repo_path=repo_path,
                files_total=1,
                started_at=time.time(),
            )

        try:
            if deleted:
                async with db_session() as session:
                    await DepStore(session).delete_file(file_path)
                    await HashStore(session).delete(file_path)
                    from app.store.node_store import NodeStore
                    from app.store.edge_store import EdgeStore
                    await NodeStore(session).delete_by_file(file_path)
                    await EdgeStore(session).delete_by_file(file_path)
                self.progress.files_done = 1
            else:
                sha = __import__("app.store.hash_store", fromlist=["compute_sha256"]).compute_sha256(file_path)
                # Check if actually changed
                async with db_session() as session:
                    stored_sha = await HashStore(session).get_hash(file_path)

                if stored_sha == sha:
                    logger.debug("Incremental: no change in %s", file_path)
                    self.progress.status = IndexStatus.COMPLETED
                    self.progress.files_skipped = 1
                    self.progress.completed_at = time.time()
                    return self.progress

                # Propagate dirty set
                dirty: Set[str] = {file_path}
                current_hashes = {file_path: sha}
                language_map = {
                    file_path: EXT_MAP.get(Path(file_path).suffix.lower(), "unknown")
                }

                async with db_session() as session:
                    dirty = await DepStore(session).expand_dirty_set(dirty)
                    # add current hashes for propagated files
                    for fp in dirty - {file_path}:
                        from app.store.hash_store import compute_sha256 as cs
                        current_hashes[fp] = cs(fp)
                        language_map[fp] = EXT_MAP.get(Path(fp).suffix.lower(), "unknown")

                    builder = GraphBuilder(session, repo_path)
                    stats = await builder.build_dirty_set(dirty, current_hashes, language_map)

                self.progress.nodes_created = stats["nodes"]
                self.progress.edges_created = stats["edges"]
                self.progress.files_done = stats["files"]

            self.progress.status = IndexStatus.COMPLETED
            self.progress.completed_at = time.time()

        except Exception as exc:
            logger.error("Incremental index failed for %s: %s", file_path, exc)
            self.progress.status = IndexStatus.FAILED
            self.progress.error_message = str(exc)
            self.progress.completed_at = time.time()

        return self.progress

    # ── DB run tracking ───────────────────────────────────────────────────────
    async def _start_run(self, run_type: str, repo_path: str) -> int:
        async with db_session() as session:
            result = await session.execute(
                text(
                    "INSERT INTO index_runs (run_type, repo_path) VALUES (:rt, :rp)"
                ),
                {"rt": run_type, "rp": repo_path},
            )
            return result.lastrowid

    async def _complete_run(self, run_id: int, prog: IndexProgress) -> None:
        async with db_session() as session:
            await session.execute(
                text(
                    """UPDATE index_runs SET
                        status='COMPLETED', files_scanned=:fs, files_indexed=:fi,
                        files_skipped=:fsk, nodes_created=:nc, edges_created=:ec,
                        duration_ms=:dur, completed_at=CURRENT_TIMESTAMP
                       WHERE id=:id"""
                ),
                {
                    "fs": prog.files_total,
                    "fi": prog.files_done,
                    "fsk": prog.files_skipped,
                    "nc": prog.nodes_created,
                    "ec": prog.edges_created,
                    "dur": prog.elapsed_ms,
                    "id": run_id,
                },
            )

    async def _fail_run(self, run_id: int, error: str) -> None:
        async with db_session() as session:
            await session.execute(
                text(
                    "UPDATE index_runs SET status='FAILED', error_message=:e, "
                    "completed_at=CURRENT_TIMESTAMP WHERE id=:id"
                ),
                {"e": error[:2000], "id": run_id},
            )
