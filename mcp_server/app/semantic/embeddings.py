"""
Semantic search over symbols using local sentence-transformers embeddings.

Design:
  - Embeddings are stored in a separate `node_embeddings` table (created on demand).
  - The model (all-MiniLM-L6-v2, 384-dim, ~90MB) is lazy-loaded on first use.
  - At query time, all vectors are loaded into a NumPy matrix once, cached in-process,
    and refreshed when the row count changes. Good up to ~1M symbols on a laptop.
  - If sentence-transformers isn't installed the module reports unavailable cleanly;
    the rest of the server keeps working.

Table (MySQL):
  CREATE TABLE node_embeddings (
    node_id VARCHAR(64) PRIMARY KEY,
    vec     BLOB NOT NULL,             -- float32 * dim, little-endian
    model   VARCHAR(64) NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (node_id) REFERENCES nodes(id) ON DELETE CASCADE
  );
"""
from __future__ import annotations
import logging
import struct
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DIM = 384

# Lazily-loaded singletons
_model = None
_np = None
_matrix = None          # (N, DIM) float32 matrix; row i corresponds to _ids[i]
_ids: List[str] = []    # parallel to _matrix rows
_cached_row_count = -1  # last time we loaded the matrix


def _get_numpy():
    global _np
    if _np is None:
        import numpy as np  # type: ignore
        _np = np
    return _np


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer  # type: ignore
        logger.info("Loading embedding model %s …", MODEL_NAME)
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def is_available() -> bool:
    """True if the required optional deps are installed."""
    try:
        import sentence_transformers  # noqa: F401
        import numpy  # noqa: F401
        return True
    except ImportError:
        return False


def _pack(vec) -> bytes:
    np = _get_numpy()
    arr = np.asarray(vec, dtype=np.float32)
    assert arr.shape == (DIM,), f"expected {DIM}-dim, got {arr.shape}"
    return arr.tobytes()


def _unpack(blob: bytes):
    np = _get_numpy()
    return np.frombuffer(blob, dtype=np.float32)


def _embed_text_for(node: dict) -> str:
    """Build the text that represents a node for embedding."""
    parts = [node.get("qualified_name") or node.get("name") or ""]
    if node.get("signature"):
        parts.append(node["signature"])
    if node.get("docstring"):
        parts.append(node["docstring"][:240])
    return " | ".join(p for p in parts if p)


async def ensure_table(db: AsyncSession) -> None:
    """Create the embeddings table if it doesn't exist (idempotent)."""
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS node_embeddings (
              node_id VARCHAR(64) NOT NULL PRIMARY KEY,
              vec     BLOB NOT NULL,
              model   VARCHAR(64) NOT NULL,
              updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP,
              FOREIGN KEY (node_id) REFERENCES nodes(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
    )
    await db.commit()


async def reindex(db: AsyncSession, batch_size: int = 64) -> Dict[str, Any]:
    """
    Compute embeddings for all nodes that don't have one yet (or whose model tag
    doesn't match the current model).
    """
    if not is_available():
        return {"ok": False, "error": "sentence-transformers not installed"}

    await ensure_table(db)
    np = _get_numpy()
    model = _get_model()

    # Find stale nodes: those without an embedding or with a different model.
    r = await db.execute(
        text(
            """
            SELECT n.id, n.name, n.qualified_name, n.signature, n.docstring
            FROM nodes n
            LEFT JOIN node_embeddings e ON e.node_id = n.id
            WHERE n.type != 'FILE'
              AND (e.node_id IS NULL OR e.model != :m)
            """
        ),
        {"m": MODEL_NAME},
    )
    rows = r.fetchall()
    total = len(rows)
    if total == 0:
        return {"ok": True, "embedded": 0, "total_nodes": 0, "model": MODEL_NAME}

    written = 0
    for start in range(0, total, batch_size):
        batch = rows[start:start + batch_size]
        texts = [
            _embed_text_for({
                "name": b[1], "qualified_name": b[2],
                "signature": b[3], "docstring": b[4],
            })
            for b in batch
        ]
        vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        for (nid, *_), v in zip(batch, vecs):
            await db.execute(
                text(
                    "INSERT INTO node_embeddings (node_id, vec, model) "
                    "VALUES (:id, :v, :m) "
                    "ON DUPLICATE KEY UPDATE vec=VALUES(vec), model=VALUES(model)"
                ),
                {"id": nid, "v": _pack(v), "m": MODEL_NAME},
            )
        await db.commit()
        written += len(batch)

    # Invalidate cache
    global _matrix, _ids, _cached_row_count
    _matrix = None
    _ids = []
    _cached_row_count = -1

    return {"ok": True, "embedded": written, "total_nodes": total, "model": MODEL_NAME}


async def _load_matrix(db: AsyncSession) -> bool:
    """Load all embeddings into memory. Refreshes when the row count changes."""
    global _matrix, _ids, _cached_row_count
    np = _get_numpy()

    r = await db.execute(text("SELECT COUNT(*) FROM node_embeddings"))
    count = r.scalar() or 0
    if count == 0:
        _matrix = None
        _ids = []
        _cached_row_count = 0
        return False
    if count == _cached_row_count and _matrix is not None:
        return True

    r = await db.execute(
        text("SELECT node_id, vec FROM node_embeddings WHERE model = :m"),
        {"m": MODEL_NAME},
    )
    ids: List[str] = []
    rows = []
    for nid, blob in r.fetchall():
        ids.append(nid)
        rows.append(_unpack(blob))
    if not rows:
        _matrix = None
        _ids = []
        _cached_row_count = 0
        return False
    _matrix = np.vstack(rows).astype(np.float32)
    _ids = ids
    _cached_row_count = count
    return True


async def search(
    db: AsyncSession, query: str, k: int = 10, symbol_type: Optional[str] = None
) -> List[Tuple[str, float]]:
    """
    Return top-k (node_id, score) where score is cosine similarity in [-1, 1].
    Symbols are re-ranked by type filter applied post-similarity.
    """
    if not is_available():
        return []
    if not await _load_matrix(db):
        return []
    model = _get_model()
    np = _get_numpy()

    q = model.encode([query], normalize_embeddings=True, show_progress_bar=False)[0]
    sims = _matrix @ q  # cosine since rows are L2-normalized
    # Top-k without a full sort
    top_n = min(max(k * 4, k), len(sims))  # oversample to allow type filtering
    idx = np.argpartition(-sims, top_n - 1)[:top_n]
    idx = idx[np.argsort(-sims[idx])]

    results = [(_ids[int(i)], float(sims[int(i)])) for i in idx]
    if symbol_type:
        # Filter by type — need a quick lookup
        ph = ",".join([f":id{i}" for i in range(len(results))])
        params = {f"id{i}": r[0] for i, r in enumerate(results)}
        params["t"] = symbol_type.upper()
        r = await db.execute(
            text(f"SELECT id FROM nodes WHERE id IN ({ph}) AND type = :t"),
            params,
        )
        allowed = {row[0] for row in r.fetchall()}
        results = [r for r in results if r[0] in allowed]
    return results[:k]
