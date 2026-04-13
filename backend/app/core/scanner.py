from __future__ import annotations
import fnmatch
import logging
from pathlib import Path
from typing import Dict, Iterator, List, Set

from app.config import settings
from app.store.hash_store import compute_sha256

logger = logging.getLogger(__name__)


class RepoScanner:
    """
    Walks a repository directory and returns source files.
    Respects ignore patterns and size limits.
    """

    def __init__(
        self,
        repo_path: str | Path,
        ignore_dirs: List[str] | None = None,
        ignore_file_patterns: List[str] | None = None,
        supported_extensions: Dict[str, str] | None = None,
        max_file_size_kb: int = 512,
    ) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.ignore_dirs: Set[str] = set(ignore_dirs or settings.IGNORE_DIRS)
        self.ignore_patterns: List[str] = ignore_file_patterns or settings.IGNORE_FILE_PATTERNS
        self.extensions: Dict[str, str] = supported_extensions or settings.SUPPORTED_EXTENSIONS
        self.max_bytes = max_file_size_kb * 1024

    def _should_ignore_dir(self, name: str) -> bool:
        return name in self.ignore_dirs or name.startswith(".")

    def _should_ignore_file(self, name: str) -> bool:
        for pat in self.ignore_patterns:
            if fnmatch.fnmatch(name, pat):
                return True
        return False

    def iter_files(self) -> Iterator[Path]:
        """Yield every supported source file under repo_path."""
        for item in self.repo_path.rglob("*"):
            if not item.is_file():
                continue
            # check if any parent directory should be ignored
            rel = item.relative_to(self.repo_path)
            if any(self._should_ignore_dir(part) for part in rel.parts[:-1]):
                continue
            if self._should_ignore_file(item.name):
                continue
            if item.suffix.lower() not in self.extensions:
                continue
            try:
                if item.stat().st_size > self.max_bytes:
                    logger.debug("Skipping large file: %s", item)
                    continue
            except OSError:
                continue
            yield item

    def scan_with_hashes(self) -> Dict[str, str]:
        """
        Returns {abs_path_str: sha256} for every discovered file.
        sha256 is empty string if file cannot be read.
        """
        result: Dict[str, str] = {}
        for path in self.iter_files():
            result[str(path)] = compute_sha256(path)
        logger.info("Scanned %d files in %s", len(result), self.repo_path)
        return result

    def detect_languages(self) -> Dict[str, int]:
        """Return {language: file_count}."""
        counts: Dict[str, int] = {}
        for path in self.iter_files():
            lang = self.extensions.get(path.suffix.lower(), "unknown")
            counts[lang] = counts.get(lang, 0) + 1
        return counts
