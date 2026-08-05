"""Pick a backend based on settings.

Doing this in a tiny factory keeps the rest of the code path-agnostic and
makes it easy to add new backends (DuckDB, Kuzu, Neo4j, ...) later.
"""
from __future__ import annotations

from typing import Optional

from ckg.config import settings
from ckg.core.errors import ConfigError
from ckg.store.base import GraphStore


async def open_store(backend: Optional[str] = None) -> GraphStore:
    """Open + initialize a graph store. Backend name defaults to settings."""
    name = (backend or settings.STORE_BACKEND).lower()

    if name == "sqlite":
        from ckg.store.sqlite import SQLiteGraphStore

        store: GraphStore = SQLiteGraphStore(settings.SQLITE_PATH)
    elif name == "mysql":
        from ckg.store.mysql import MySQLGraphStore

        store = MySQLGraphStore(settings.DATABASE_URL)
    else:
        raise ConfigError(f"Unknown STORE_BACKEND: {name!r}. Use 'sqlite' or 'mysql'.")

    await store.init()
    return store
