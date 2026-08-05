"""Typed exceptions so callers can distinguish parser, store, and config failures."""
from __future__ import annotations


class CKGError(Exception):
    """Base class for every CKG-raised exception."""


class ParseError(CKGError):
    """A parser failed for a specific file. Wraps the original error."""

    def __init__(self, file_path: str, message: str) -> None:
        super().__init__(f"{file_path}: {message}")
        self.file_path = file_path
        self.message = message


class StoreError(CKGError):
    """A storage backend operation failed."""


class ConfigError(CKGError):
    """A configuration value is missing or invalid."""


class IndexerError(CKGError):
    """Top-level indexing failure (orchestration, not a single file)."""
