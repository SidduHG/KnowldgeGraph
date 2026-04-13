from __future__ import annotations
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import HealthResponse, StatsResponse
from app.config import settings
from app.database.connection import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/status", tags=["status"])


@router.get("/health", response_model=HealthResponse)
async def health(db: AsyncSession = Depends(get_db)) -> Any:
    db_status = "ok"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"error: {exc}"
    return HealthResponse(ok=db_status == "ok", version=settings.APP_VERSION, db=db_status)


@router.get("", response_model=StatsResponse)
async def stats(db: AsyncSession = Depends(get_db)) -> Any:
    # total files
    r = await db.execute(text("SELECT COUNT(*) FROM file_hashes"))
    total_files = r.scalar() or 0

    # total nodes
    r = await db.execute(text("SELECT COUNT(*) FROM nodes"))
    total_nodes = r.scalar() or 0

    # total edges
    r = await db.execute(text("SELECT COUNT(*) FROM edges"))
    total_edges = r.scalar() or 0

    # node breakdown
    r = await db.execute(text("SELECT type, COUNT(*) FROM nodes GROUP BY type"))
    node_types = {row[0]: row[1] for row in r.fetchall()}

    # edge breakdown
    r = await db.execute(text("SELECT type, COUNT(*) FROM edges GROUP BY type"))
    edge_types = {row[0]: row[1] for row in r.fetchall()}

    # last completed run
    r = await db.execute(
        text(
            "SELECT run_type, status, files_indexed, nodes_created, edges_created, "
            "duration_ms, started_at FROM index_runs "
            "ORDER BY id DESC LIMIT 1"
        )
    )
    row = r.fetchone()
    last_run: Optional[dict] = None
    if row:
        last_run = {
            "run_type": row[0],
            "status": row[1],
            "files_indexed": row[2],
            "nodes_created": row[3],
            "edges_created": row[4],
            "duration_ms": row[5],
            "started_at": str(row[6]),
        }

    return StatsResponse(
        total_files=total_files,
        total_nodes=total_nodes,
        total_edges=total_edges,
        node_types=node_types,
        edge_types=edge_types,
        last_run=last_run,
    )
