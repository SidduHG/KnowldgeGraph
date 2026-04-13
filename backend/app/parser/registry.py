from __future__ import annotations
import logging
from pathlib import Path
from typing import Dict, Optional

from app.parser.base import BaseParser, ParseResult

logger = logging.getLogger(__name__)

# Extension → language
EXT_MAP: Dict[str, str] = {
    ".py":  "python",
    ".ts":  "typescript",
    ".tsx": "typescript",
    ".js":  "javascript",
    ".jsx": "javascript",
}


class ParserRegistry:
    """Lazy-loads one parser instance per language."""

    def __init__(self) -> None:
        self._parsers: Dict[str, BaseParser] = {}

    def _load(self, language: str) -> Optional[BaseParser]:
        if language == "python":
            try:
                from app.parser.languages.python_parser import PythonParser
                return PythonParser()
            except Exception as exc:
                logger.error("Failed to load Python parser: %s", exc)
                return None

        if language == "typescript":
            try:
                from app.parser.languages.typescript_parser import TypeScriptParser
                return TypeScriptParser()
            except Exception as exc:
                logger.error("Failed to load TypeScript parser: %s", exc)
                return None

        if language == "javascript":
            # Re-use TypeScript parser (TS grammar is a superset)
            try:
                from app.parser.languages.typescript_parser import TypeScriptParser
                return TypeScriptParser()
            except Exception as exc:
                logger.error("Failed to load JS parser: %s", exc)
                return None

        return None

    def get(self, language: str) -> Optional[BaseParser]:
        if language not in self._parsers:
            parser = self._load(language)
            if parser:
                self._parsers[language] = parser
        return self._parsers.get(language)

    def parse_file(self, file_path: str | Path) -> Optional[ParseResult]:
        path = Path(file_path)
        language = EXT_MAP.get(path.suffix.lower())
        if not language:
            return None
        parser = self.get(language)
        if not parser:
            return None
        return parser.parse_file(path)

    @property
    def supported_extensions(self) -> list[str]:
        return list(EXT_MAP.keys())


# Singleton
registry = ParserRegistry()
