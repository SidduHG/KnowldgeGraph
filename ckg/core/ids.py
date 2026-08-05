"""Deterministic IDs for nodes and edges.

Same inputs always produce the same ID — this is what makes upserts
idempotent and lets us re-index without creating duplicates.
"""
from __future__ import annotations

import hashlib

_HASH_LEN = 32  # 128 bits — collision-safe for the largest expected repos


def node_id(file_path: str, qualified_name: str, node_type: str) -> str:
    """Stable hash for a symbol.

    The triple (file_path, qualified_name, type) uniquely identifies a node.
    Using a stable triple means re-running the indexer on unchanged code
    produces identical IDs — the upsert just bumps timestamps.
    """
    raw = f"{file_path}::{qualified_name}::{node_type}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:_HASH_LEN]


def edge_id(source_id: str, target_id: str, edge_type: str) -> str:
    """Stable hash for a relationship between two nodes."""
    raw = f"{source_id}->{target_id}::{edge_type}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:_HASH_LEN]
