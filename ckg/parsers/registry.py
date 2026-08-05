"""Decorator-based parser registry.

Languages register themselves at import time via ``@register("python")``.
Lookup is by language string OR by file extension. Adding a new language
no longer requires editing this file.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Optional, Type, Union

from ckg.config import settings
from ckg.core import ParseResult
from ckg.observability import get_logger
from ckg.parsers.base import BaseParser

logger = get_logger(__name__)

# language → parser class (instantiated lazily)
_PARSER_CLASSES: Dict[str, Type[BaseParser]] = {}
# language → instance (cached after first use)
_PARSER_INSTANCES: Dict[str, Optional[BaseParser]] = {}

# Public — extension to language map. Comes from settings so users can extend it.
EXT_MAP: Dict[str, str] = settings.SUPPORTED_EXTENSIONS


def register(language: str) -> Callable[[Type[BaseParser]], Type[BaseParser]]:
    """Class decorator that registers a parser for a language identifier."""

    def _decorator(cls: Type[BaseParser]) -> Type[BaseParser]:
        cls.language = language
        _PARSER_CLASSES[language] = cls
        return cls

    return _decorator


def get_parser(language: str) -> Optional[BaseParser]:
    """Lazy-instantiate (and cache) the parser for ``language``."""
    if language in _PARSER_INSTANCES:
        return _PARSER_INSTANCES[language]

    cls = _PARSER_CLASSES.get(language)
    if cls is None:
        _PARSER_INSTANCES[language] = None
        return None

    try:
        instance = cls()
    except Exception as exc:  # pragma: no cover — env-dependent
        logger.warning("Failed to load %s parser: %s", language, exc)
        _PARSER_INSTANCES[language] = None
        return None

    _PARSER_INSTANCES[language] = instance
    return instance


def parse_file(file_path: Union[str, Path]) -> Optional[ParseResult]:
    """Convenience: dispatch to the parser registered for ``file_path``'s extension."""
    path = Path(file_path)
    language = EXT_MAP.get(path.suffix.lower())
    if language is None:
        return None
    parser = get_parser(language)
    if parser is None:
        return None
    return parser.parse_file(path)


def supported_languages() -> list[str]:
    """Languages that have a parser class registered (regardless of grammar availability)."""
    return sorted(_PARSER_CLASSES.keys())
