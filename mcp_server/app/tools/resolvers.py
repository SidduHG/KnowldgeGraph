"""
All 6 knowledge-graph resolvers.
Each returns a plain Python dict — the formatter decides how to serialise it.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)

# ── helpers ───────────────────────────────────────────────────────────────────

def _node_cols() -> str:
    return ("id,type,name,qualified_name,file_path,"
            "start_line,end_line,signature,docstring,language")

def _row_to_node(row: tuple) -> dict:
    keys = ["id","type","name","qualified_name","file_path",
            "start_line","end_line","signature","docstring","language"]
    return dict(zip(keys, row))


# ── 1. get_function ───────────────────────────────────────────────────────────

async def get_function(db: AsyncSession, name: str) -> Dict[str, Any]:
    """
    Return full details of a function/method/class by name or qualified name.
    Searches name first, then qualified_name.
    """
    r = await db.execute(
        text(
            f"SELECT {_node_cols()} FROM nodes "
            "WHERE (name = :n OR qualified_name LIKE :qn) "
            "AND type IN ('FUNCTION','METHOD','CLASS') "
            f"ORDER BY CHAR_LENGTH(name) LIMIT {settings.MAX_RESULTS}"
        ),
        {"n": name, "qn": f"%{name}%"},
    )
    rows = r.fetchall()
    if not rows:
        return {"found": False, "query": name}
    return {
        "found": True,
        "count": len(rows),
        "results": [_row_to_node(row) for row in rows],
    }


# ── 2. get_callers ────────────────────────────────────────────────────────────

async def get_callers(db: AsyncSession, name: str) -> Dict[str, Any]:
    """
    Return all functions/methods that call `name`.
    """
    # Find target node(s)
    r = await db.execute(
        text(f"SELECT id,name,file_path FROM nodes WHERE name = :n LIMIT 5"),
        {"n": name},
    )
    targets = r.fetchall()
    if not targets:
        return {"found": False, "query": name}

    target_ids = [t[0] for t in targets]
    ph = ",".join([f":id{i}" for i in range(len(target_ids))])
    id_params = {f"id{i}": v for i, v in enumerate(target_ids)}

    r = await db.execute(
        text(
            f"SELECT n.{_node_cols()} FROM edges e "
            f"JOIN nodes n ON n.id = e.source_id "
            f"WHERE e.target_id IN ({ph}) AND e.type = 'CALLS' "
            f"ORDER BY n.file_path LIMIT {settings.MAX_RESULTS}"
        ),
        id_params,
    )
    callers = [_row_to_node(row) for row in r.fetchall()]
    return {
        "found": True,
        "target": name,
        "caller_count": len(callers),
        "callers": callers,
    }


# ── 3. get_callees ────────────────────────────────────────────────────────────

async def get_callees(db: AsyncSession, name: str) -> Dict[str, Any]:
    """
    Return all functions/methods called by `name`.
    """
    r = await db.execute(
        text(f"SELECT id FROM nodes WHERE name = :n LIMIT 5"),
        {"n": name},
    )
    sources = r.fetchall()
    if not sources:
        return {"found": False, "query": name}

    source_ids = [s[0] for s in sources]
    ph = ",".join([f":id{i}" for i in range(len(source_ids))])
    id_params = {f"id{i}": v for i, v in enumerate(source_ids)}

    r = await db.execute(
        text(
            f"SELECT n.{_node_cols()} FROM edges e "
            f"JOIN nodes n ON n.id = e.target_id "
            f"WHERE e.source_id IN ({ph}) AND e.type = 'CALLS' "
            f"ORDER BY n.file_path LIMIT {settings.MAX_RESULTS}"
        ),
        id_params,
    )
    callees = [_row_to_node(row) for row in r.fetchall()]
    return {
        "found": True,
        "source": name,
        "callee_count": len(callees),
        "callees": callees,
    }


# ── 4. get_file_map ───────────────────────────────────────────────────────────

async def get_file_map(db: AsyncSession, file_path: str) -> Dict[str, Any]:
    """
    Return all symbols defined in a file — ordered by line.
    """
    r = await db.execute(
        text(
            f"SELECT {_node_cols()} FROM nodes "
            "WHERE file_path = :fp OR file_path LIKE :fp_like "
            f"ORDER BY start_line LIMIT {settings.MAX_RESULTS * 3}"
        ),
        {"fp": file_path, "fp_like": f"%{file_path}%"},
    )
    rows = [_row_to_node(row) for row in r.fetchall()]
    if not rows:
        return {"found": False, "query": file_path}
    return {
        "found": True,
        "file_path": rows[0]["file_path"],
        "symbol_count": len(rows),
        "symbols": rows,
    }


# ── 5. search_symbol ──────────────────────────────────────────────────────────

async def search_symbol(
    db: AsyncSession,
    query: str,
    symbol_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fuzzy search across all symbol names + qualified names.
    Optional filter by type: FUNCTION | CLASS | METHOD | VARIABLE | TYPE.
    """
    type_filter = ""
    params: dict = {"q": f"%{query}%", "limit": settings.MAX_RESULTS}
    if symbol_type:
        type_filter = "AND type = :type "
        params["type"] = symbol_type.upper()

    r = await db.execute(
        text(
            f"SELECT {_node_cols()} FROM nodes "
            f"WHERE (name LIKE :q OR qualified_name LIKE :q) {type_filter}"
            "ORDER BY CHAR_LENGTH(name) LIMIT :limit"
        ),
        params,
    )
    results = [_row_to_node(row) for row in r.fetchall()]
    return {
        "query": query,
        "count": len(results),
        "results": results,
    }


# ── 6. get_related ────────────────────────────────────────────────────────────

async def get_related(db: AsyncSession, file_path: str) -> Dict[str, Any]:
    """
    Return files connected to `file_path` via import or call edges.
    Gives the AI a map of what's nearby without loading the whole graph.
    """
    # Files this file imports
    r = await db.execute(
        text(
            "SELECT importee FROM file_deps WHERE importer LIKE :fp "
            f"LIMIT {settings.MAX_RESULTS}"
        ),
        {"fp": f"%{file_path}%"},
    )
    imports = [row[0] for row in r.fetchall()]

    # Files that import this file
    r = await db.execute(
        text(
            "SELECT importer FROM file_deps WHERE importee LIKE :fp "
            f"LIMIT {settings.MAX_RESULTS}"
        ),
        {"fp": f"%{file_path}%"},
    )
    imported_by = [row[0] for row in r.fetchall()]

    return {
        "file_path": file_path,
        "imports_count": len(imports),
        "imported_by_count": len(imported_by),
        "imports": imports,
        "imported_by": imported_by,
    }
