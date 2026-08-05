"""Abstract parser interface — every language parser implements this."""
from __future__ import annotations

from pathlib import Path
from typing import Union

from ckg.core import ParseResult


class BaseParser:
    """Interface every language parser must implement."""

    language: str = "unknown"

    def parse(self, file_path: Union[str, Path], source: str) -> ParseResult:
        """Parse already-loaded source. Override this."""
        raise NotImplementedError

    def parse_file(self, file_path: Union[str, Path]) -> ParseResult:
        """Read a file from disk and parse it. Default impl is fine for most languages."""
        path = Path(file_path)
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            res = ParseResult(file_path=str(path), language=self.language)
            res.error = f"read failed: {exc}"
            return res
        return self.parse(path, content)
