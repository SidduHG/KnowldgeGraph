"""Repo overview tools."""
from __future__ import annotations

from typing import Any, Dict

from ckg.parsers.registry import EXT_MAP, supported_languages
from ckg.store.base import GraphStore


async def get_stats(store: GraphStore) -> Dict[str, Any]:
    return await store.stats()


async def list_languages(store: GraphStore) -> Dict[str, Any]:
    """Languages that have parsers + actual files seen in the graph."""
    s = await store.stats()
    return {
        "registered_parsers": supported_languages(),
        "extensions": EXT_MAP,
        "languages_in_graph": s.get("languages", []),
    }
