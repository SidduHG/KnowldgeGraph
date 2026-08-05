"""Repo scanner — walks the directory and computes file hashes.

Pulled out so it can be tested without spinning up the indexer.
"""
from __future__ import annotations

import fnmatch
import hashlib
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Set, Union

from ckg.config import settings
from ckg.observability import counter, get_logger

logger = get_logger(__name__)
_SCAN_FILES = counter("ckg_scan_files_total", "Files visited by RepoScanner")


def compute_sha256(path: Union[str, Path]) -> str:
    """Streaming SHA-256 — handles files much larger than RAM."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError as exc:
        logger.warning("Cannot hash %s: %s", path, exc)
        return ""


class RepoScanner:
    """Yields source files under a repo, respecting ignore rules + size limits."""

    def __init__(
        self,
        repo_path: Union[str, Path],
        *,
        ignore_dirs: Optional[Iterable[str]] = None,
        ignore_file_patterns: Optional[Iterable[str]] = None,
        supported_extensions: Optional[Dict[str, str]] = None,
        max_file_size_kb: Optional[int] = None,
    ) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.ignore_dirs: Set[str] = set(ignore_dirs or settings.IGNORE_DIRS)
        self.ignore_patterns: List[str] = list(
            ignore_file_patterns or settings.IGNORE_FILE_PATTERNS
        )
        self.extensions: Dict[str, str] = dict(
            supported_extensions or settings.SUPPORTED_EXTENSIONS
        )
        self.max_bytes = (max_file_size_kb or settings.MAX_FILE_SIZE_KB) * 1024

    # ── Filters ──────────────────────────────────────────────────────────────
    def _ignore_dir(self, name: str) -> bool:
        return name in self.ignore_dirs or name.startswith(".")

    def _ignore_file(self, name: str) -> bool:
        return any(fnmatch.fnmatch(name, p) for p in self.ignore_patterns)

    # ── Iteration ────────────────────────────────────────────────────────────
    def iter_files(self) -> Iterator[Path]:
        for item in self.repo_path.rglob("*"):
            if not item.is_file():
                continue
            rel = item.relative_to(self.repo_path)
            if any(self._ignore_dir(part) for part in rel.parts[:-1]):
                continue
            if self._ignore_file(item.name):
                continue
            if item.suffix.lower() not in self.extensions:
                continue
            try:
                if item.stat().st_size > self.max_bytes:
                    logger.debug("Skipping large file: %s", item)
                    continue
            except OSError:
                continue
            _SCAN_FILES.inc()
            yield item

    def scan_with_hashes(self) -> Dict[str, str]:
        """``{abs_path: sha256}`` for every supported source file."""
        result: Dict[str, str] = {}
        for path in self.iter_files():
            result[str(path)] = compute_sha256(path)
        logger.info("Scanned %d files in %s", len(result), self.repo_path)
        return result

    def language_breakdown(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for path in self.iter_files():
            lang = self.extensions.get(path.suffix.lower(), "unknown")
            counts[lang] = counts.get(lang, 0) + 1
        return counts
