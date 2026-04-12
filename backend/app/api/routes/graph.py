from __future__ import annotations
import logging
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import EdgeOut, FileMapResponse, NodeOut
from app.database.connection import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/graph", tags=["graph"])


def _row_to_node(row: tuple) -> NodeOut:
    keys = ["id","type","name","qualified_name","file_path",
            "start_line","end_line","signature","docstring","language"]
    return NodeOut(**dict(zip(keys, row)))


def _row_to_edge(row: tuple) -> EdgeOut:
    return EdgeOut(id=row[0], source_id=row[1], target_id=row[2],
                   type=row[3], file_path=row[4])


@router.get("/nodes", response_model=List[NodeOut])
async def list_nodes(
    type: str | None = Query(None),
    language: str | None = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
) -> Any:
    wheres = []
    params: dict = {"limit": limit, "offset": offset}
    if type:
        wheres.append("type = :type")
        params["type"] = type.upper()
    if language:
        wheres.append("language = :language")
        params["language"] = language

    where_sql = ("WHERE " + " AND ".join(wheres)) if wheres else ""
    r = await db.execute(
        text(
            f"SELECT id,type,name,qualified_name,file_path,start_line,end_line,"
            f"signature,docstring,language FROM nodes {where_sql} "
            f"ORDER BY file_path,start_line LIMIT :limit OFFSET :offset"
        ),
        params,
    )
    return [_row_to_node(row) for row in r.fetchall()]


@router.get("/nodes/search", response_model=List[NodeOut])
async def search_nodes(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
) -> Any:
    r = await db.execute(
        text(
            "SELECT id,type,name,qualified_name,file_path,start_line,end_line,"
            "signature,docstring,language FROM nodes "
            "WHERE name LIKE :q OR qualified_name LIKE :q "
            "ORDER BY CHAR_LENGTH(name) LIMIT :limit"
        ),
        {"q": f"%{q}%", "limit": limit},
    )
    return [_row_to_node(row) for row in r.fetchall()]


@router.get("/nodes/{node_id}", response_model=NodeOut)
async def get_node(node_id: str, db: AsyncSession = Depends(get_db)) -> Any:
    r = await db.execute(
        text(
            "SELECT id,type,name,qualified_name,file_path,start_line,end_line,"
            "signature,docstring,language FROM nodes WHERE id = :id"
        ),
        {"id": node_id},
    )
    row = r.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Node not found")
    return _row_to_node(row)


@router.get("/edges", response_model=List[EdgeOut])
async def list_edges(
    source_id: str | None = Query(None),
    target_id: str | None = Query(None),
    type: str | None = Query(None),
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
) -> Any:
    wheres = []
    params: dict = {"limit": limit}
    if source_id:
        wheres.append("source_id = :source_id")
        params["source_id"] = source_id
    if target_id:
        wheres.append("target_id = :target_id")
        params["target_id"] = target_id
    if type:
        wheres.append("type = :type")
        params["type"] = type.upper()

    where_sql = ("WHERE " + " AND ".join(wheres)) if wheres else ""
    r = await db.execute(
        text(
            f"SELECT id,source_id,target_id,type,file_path FROM edges "
            f"{where_sql} LIMIT :limit"
        ),
        params,
    )
    return [_row_to_edge(row) for row in r.fetchall()]


@router.get("/file", response_model=FileMapResponse)
async def get_file_map(
    path: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> Any:
    r = await db.execute(
        text(
            "SELECT id,type,name,qualified_name,file_path,start_line,end_line,"
            "signature,docstring,language FROM nodes WHERE file_path = :fp "
            "ORDER BY start_line"
        ),
        {"fp": path},
    )
    nodes = [_row_to_node(row) for row in r.fetchall()]
    if not nodes:
        raise HTTPException(status_code=404, detail="File not found in graph")

    node_ids = [n.id for n in nodes]
    placeholders = ",".join([f":id{i}" for i in range(len(node_ids))])
    id_params = {f"id{i}": v for i, v in enumerate(node_ids)}
    r = await db.execute(
        text(
            f"SELECT id,source_id,target_id,type,file_path FROM edges "
            f"WHERE source_id IN ({placeholders}) OR target_id IN ({placeholders})"
        ),
        id_params,
    )
    edges = [_row_to_edge(row) for row in r.fetchall()]
    return FileMapResponse(file_path=path, nodes=nodes, edges=edges)
