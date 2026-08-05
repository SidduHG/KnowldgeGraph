"""Storage backends.

The store package defines a single ``GraphStore`` Protocol; concrete
implementations live in ``sqlite.py`` and ``mysql.py``. The indexer and MCP
tools depend only on the Protocol — they don't import a specific backend.
"""
from ckg.store.base import (
    EdgeRecord,
    FileHashRecord,
    GraphStore,
    NodeRecord,
)
from ckg.store.factory import open_store

__all__ = [
    "EdgeRecord",
    "FileHashRecord",
    "GraphStore",
    "NodeRecord",
    "open_store",
]
