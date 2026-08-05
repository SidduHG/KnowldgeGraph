"""Indexer orchestration — full + incremental runs, dirty-set propagation,
co-operative async yielding so HTTP polls stay responsive during long runs.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Set

from ckg.config import settings
from ckg.indexer.builder import GraphBuilder
from ckg.indexer.scanner import RepoScanner, compute_sha256
from ckg.observability import counter, get_logger
from ckg.parsers.registry import EXT_MAP
from ckg.store.base import GraphStore

logger = get_logger(__name__)
_RUNS = counter("ckg_index_runs_total", "Indexer runs by type and status")


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
        return int(self.files_done / self.files_total * 100) if self.files_total else 0


class IndexerService:
    """Per-process singleton — owns the indexing state machine."""

    _instance: Optional["IndexerService"] = None

    def __init__(self, store: GraphStore) -> None:
        self._store = store
        self.progress = IndexProgress()
        self._lock = asyncio.Lock()
        self._current_repo: Optional[str] = None

    @classmethod
    def get(cls, store: Optional[GraphStore] = None) -> "IndexerService":
        if cls._instance is None:
            if store is None:
                raise RuntimeError("IndexerService.get(store=...) must be passed a store the first time")
            cls._instance = cls(store)
        return cls._instance

    @property
    def is_running(self) -> bool:
        return self.progress.status is IndexStatus.RUNNING

    def reset(self) -> None:
        logger.warning("Force-resetting indexer from %s", self.progress.status)
        self.progress = IndexProgress()
        self._lock = asyncio.Lock()

    # ── Full index ───────────────────────────────────────────────────────────
    async def run_full(self, repo_path: str) -> IndexProgress:
        if self._lock.locked():
            return self.progress

        async with self._lock:
            self.progress = IndexProgress(
                status=IndexStatus.RUNNING, run_type="FULL",
                repo_path=repo_path, started_at=time.time(),
            )

        if self._current_repo and self._current_repo != repo_path:
            logger.info("Repo changed → wiping previous graph")
            await self._store.clear_all()
        self._current_repo = repo_path

        try:
            scanner = RepoScanner(repo_path)
            current = await asyncio.get_event_loop().run_in_executor(
                None, scanner.scan_with_hashes
            )
            language_map = {
                fp: EXT_MAP.get(Path(fp).suffix.lower(), "unknown") for fp in current
            }

            dirty = set(current.keys())
            self.progress.files_total = len(dirty)
            await asyncio.sleep(0)

            dirty = await self._store.expand_dirty_set(dirty)
            builder = GraphBuilder(self._store, repo_path)

            total = {"nodes": 0, "edges": 0, "files": 0, "errors": 0}
            for i, fp in enumerate(sorted(dirty)):
                sha = current.get(fp, "")
                lang = language_map.get(fp, "unknown")
                try:
                    s = await builder.build_file(fp, sha, lang)
                    total["nodes"] += s["nodes"]
                    total["edges"] += s["edges"]
                    total["files"] += 1
                except Exception as exc:
                    logger.error("Build failed for %s: %s", fp, exc)
                    total["errors"] += 1

                self.progress.files_done = total["files"]
                self.progress.nodes_created = total["nodes"]
                self.progress.edges_created = total["edges"]
                self.progress.errors = total["errors"]

                if (i + 1) % settings.YIELD_EVERY_FILES == 0:
                    await asyncio.sleep(0)

            self.progress.status = IndexStatus.COMPLETED
            self.progress.completed_at = time.time()
            _RUNS.inc(labels={"type": "full", "status": "ok"})
            logger.info(
                "✓ Full index: %d files, %d nodes, %d edges in %.1fs",
                total["files"], total["nodes"], total["edges"],
                self.progress.elapsed_ms / 1000,
            )

        except Exception as exc:
            logger.error("Full index failed: %s", exc, exc_info=True)
            self.progress.status = IndexStatus.FAILED
            self.progress.error_message = str(exc)
            self.progress.completed_at = time.time()
            _RUNS.inc(labels={"type": "full", "status": "fail"})

        return self.progress

    # ── Incremental index (single file) ──────────────────────────────────────
    async def run_incremental(
        self, file_path: str, repo_path: str, *, deleted: bool = False
    ) -> IndexProgress:
        async with self._lock:
            if self.is_running:
                return self.progress
            self.progress = IndexProgress(
                status=IndexStatus.RUNNING, run_type="INCREMENTAL",
                repo_path=repo_path, files_total=1, started_at=time.time(),
            )

        try:
            if deleted:
                await self._store.delete_file_deps(file_path)
                await self._store.delete_hash(file_path)
                await self._store.delete_nodes_by_file(file_path)
                await self._store.delete_edges_by_file(file_path)
                self.progress.files_done = 1
            else:
                sha = compute_sha256(file_path)
                if sha and await self._store.get_hash(file_path) == sha:
                    self.progress.files_skipped = 1
                    self.progress.status = IndexStatus.COMPLETED
                    self.progress.completed_at = time.time()
                    _RUNS.inc(labels={"type": "incr", "status": "skip"})
                    return self.progress

                dirty: Set[str] = await self._store.expand_dirty_set({file_path})
                current = {file_path: sha}
                language_map = {file_path: EXT_MAP.get(Path(file_path).suffix.lower(), "unknown")}
                for fp in dirty - {file_path}:
                    current[fp] = compute_sha256(fp)
                    language_map[fp] = EXT_MAP.get(Path(fp).suffix.lower(), "unknown")

                builder = GraphBuilder(self._store, repo_path)
                total = {"nodes": 0, "edges": 0, "files": 0}
                for fp in dirty:
                    s = await builder.build_file(fp, current[fp], language_map[fp])
                    total["nodes"] += s["nodes"]
                    total["edges"] += s["edges"]
                    total["files"] += 1

                self.progress.nodes_created = total["nodes"]
                self.progress.edges_created = total["edges"]
                self.progress.files_done = total["files"]

            self.progress.status = IndexStatus.COMPLETED
            self.progress.completed_at = time.time()
            _RUNS.inc(labels={"type": "incr", "status": "ok"})

        except Exception as exc:
            logger.error("Incremental index failed: %s", exc, exc_info=True)
            self.progress.status = IndexStatus.FAILED
            self.progress.error_message = str(exc)
            self.progress.completed_at = time.time()
            _RUNS.inc(labels={"type": "incr", "status": "fail"})

        return self.progress
