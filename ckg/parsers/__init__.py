"""Pluggable language parsers.

To add a language:
  1. Subclass ``ckg.parsers.treesitter.TreeSitterParser`` (or ``BaseParser``).
  2. Register it via ``@register("yourlang")`` from ``ckg.parsers.registry``.
  3. Add the file extension(s) to ``Settings.SUPPORTED_EXTENSIONS``.

Parsers receive raw source bytes and return a ``ParseResult`` — they
never touch the database or filesystem (except to read their input file).
"""
from ckg.parsers.base import BaseParser
from ckg.parsers.registry import EXT_MAP, get_parser, parse_file, register

# Trigger registration side-effects so all parsers are discoverable.
from ckg.parsers import (  # noqa: F401  (import for side-effects)
    python as _python,
    typescript as _typescript,
    go as _go,
    rust as _rust,
    java as _java,
    ruby as _ruby,
)

__all__ = ["BaseParser", "EXT_MAP", "get_parser", "parse_file", "register"]
