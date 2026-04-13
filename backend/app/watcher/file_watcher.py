from __future__ import annotations
import asyncio
import logging
import threading
import time
from pathlib import Path
from typing import Callable, Optional, Set

from watchdog.events import (
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

from app.config import settings
from app.parser.registry import EXT_MAP

logger = logging.getLogger(__name__)


class _DebouncedHandler(FileSystemEventHandler):
    """
    Watchdog handler that debounces rapid file events.
    Only triggers after DEBOUNCE_MS of silence for each path.
    """

    DEBOUNCE_S = settings.WATCHER_DEBOUNCE_MS / 1000

    def __init__(
        self,
        on_change: Callable[[str, bool], None],
        ignore_dirs: Set[str],
    ) -> None:
        super().__init__()
        self._on_change = on_change
        self._ignore_dirs = ignore_dirs
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def _is_relevant(self, path: str) -> bool:
        p = Path(path)
        if p.suffix.lower() not in EXT_MAP:
            return False
        for part in p.parts:
            if part in self._ignore_dirs or part.startswith("."):
                return False
        return True

    def _schedule(self, path: str, deleted: bool = False) -> None:
        if not self._is_relevant(path):
            return
        with self._lock:
            old = self._timers.pop(path, None)
            if old:
                old.cancel()
            t = threading.Timer(
                self.DEBOUNCE_S,
                self._on_change,
                args=(path, deleted),
            )
            self._timers[path] = t
            t.start()

    def on_created(self, event: FileCreatedEvent) -> None:
        if not event.is_directory:
            self._schedule(event.src_path)

    def on_modified(self, event: FileModifiedEvent) -> None:
        if not event.is_directory:
            self._schedule(event.src_path)

    def on_deleted(self, event: FileDeletedEvent) -> None:
        if not event.is_directory:
            self._schedule(event.src_path, deleted=True)

    def on_moved(self, event: FileMovedEvent) -> None:
        if not event.is_directory:
            self._schedule(event.src_path, deleted=True)
            self._schedule(event.dest_path, deleted=False)


class FileWatcher:
    """
    Wraps watchdog Observer and bridges sync callbacks into async coroutines.
    """

    def __init__(
        self,
        repo_path: str,
        on_change_coro: Callable,   # async (path: str, deleted: bool) -> None
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        self._repo_path = repo_path
        self._coro_callback = on_change_coro
        self._loop = loop or asyncio.get_event_loop()
        self._observer: Optional[Observer] = None

    def _sync_callback(self, path: str, deleted: bool) -> None:
        """Called from watchdog's thread — bridge to async loop."""
        future = asyncio.run_coroutine_threadsafe(
            self._coro_callback(path, deleted),
            self._loop,
        )
        try:
            future.result(timeout=30)
        except Exception as exc:
            logger.error("Watcher callback error for %s: %s", path, exc)

    def start(self) -> None:
        handler = _DebouncedHandler(
            on_change=self._sync_callback,
            ignore_dirs=set(settings.IGNORE_DIRS),
        )
        self._observer = Observer()
        self._observer.schedule(handler, self._repo_path, recursive=True)
        self._observer.start()
        logger.info("✓ Watching %s", self._repo_path)

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join()
            logger.info("File watcher stopped")
