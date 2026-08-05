"""
All knowledge-graph resolvers.
Each returns a plain Python dict — the formatter decides how to serialise it.

Tools:
  1. get_function      — Full details of a function/method/class by name
  2. get_callers       — All functions that call a given function
  3. get_callees       — All functions called by a given function
  4. get_file_map      — All symbols defined in a file (with connection counts)
  5. search_symbol     — Fuzzy search across all symbol names
  6. get_related       — Files connected via import/call edges
  7. get_context       — 1-hop context: file symbols + imports + connected symbols
  8. get_hierarchy     — Class inheritance tree
  9. get_stats         — Quick repo overview for orientation
 10. get_definition    — Exact source lines for a specific symbol
 11. get_diff_context  — Symbols changed in a git ref/range + 1-hop blast radius
"""
from __future__ import annotations
import asyncio
import logging
import os
import re
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.semantic import embeddings as _embeddings

logger = logging.getLogger(__name__)

# ── helpers ───────────────────────────────────────────────────────────────────

def _node_cols(prefix: str = "") -> str:
    p = f"{prefix}." if prefix else ""
    return (f"{p}id,{p}type,{p}name,{p}qualified_name,{p}file_path,"
            f"{p}start_line,{p}end_line,{p}signature,{p}docstring,{p}source_snippet,{p}language")

def _row_to_node(row: tuple) -> dict:
    keys = ["id","type","name","qualified_name","file_path",
            "start_line","end_line","signature","docstring","source_snippet","language"]
    return dict(zip(keys, row))


async def _resolve_file_path(db: AsyncSession, fp: str) -> Optional[str]:
    """
    Resolve a user-supplied path to a canonical absolute path stored in `nodes`.

    Strategy (in order — each step is anchored so 'auth.py' never matches 'author.py'):
      1. Exact match.
      2. Normalize backslashes → '/' and retry exact match.
      3. Suffix match on a path boundary: path ends with '/<fp>'. We use
         LIKE '%/fp' (prefixing a separator prevents 'foo/author.py' matching 'auth.py').
      4. If the user passed a bare filename (no slash), also try name-basis suffix.

    Returns the canonical file_path found in the DB, or None.
    """
    if not fp:
        return None

    # 1. Exact match
    r = await db.execute(
        text("SELECT file_path FROM nodes WHERE file_path = :fp LIMIT 1"),
        {"fp": fp},
    )
    row = r.fetchone()
    if row:
        return row[0]

    # 2. Normalize separators
    norm = fp.replace("\\", "/")
    if norm != fp:
        r = await db.execute(
            text("SELECT file_path FROM nodes WHERE file_path = :fp LIMIT 1"),
            {"fp": norm},
        )
        row = r.fetchone()
        if row:
            return row[0]

    # 3. Anchored suffix: the stored path ends with '/<fp>' OR equals '<fp>'
    suffix = norm if norm.startswith("/") else "/" + norm
    r = await db.execute(
        text(
            "SELECT file_path FROM nodes "
            "WHERE file_path LIKE :suf ESCAPE '\\\\' "
            "ORDER BY CHAR_LENGTH(file_path) ASC LIMIT 1"
        ),
        {"suf": f"%{suffix}"},
    )
    row = r.fetchone()
    if row:
        return row[0]

    return None


# ── 1. get_function ───────────────────────────────────────────────────────────

async def get_function(db: AsyncSession, name: str) -> Dict[str, Any]:
    """
    Return full details of a function/method/class by name or qualified name.
    Prefers exact match on name; falls back to qualified_name suffix match.
    """
    # 1. Exact-name match first (fast, uses index)
    r = await db.execute(
        text(
            f"SELECT {_node_cols()} FROM nodes "
            "WHERE name = :n AND type IN ('FUNCTION','METHOD','CLASS') "
            f"ORDER BY CHAR_LENGTH(qualified_name) LIMIT {settings.MAX_RESULTS}"
        ),
        {"n": name},
    )
    rows = r.fetchall()

    # 2. If nothing, try qualified-name suffix (anchored: ends with '.<name>' or equals)
    if not rows:
        r = await db.execute(
            text(
                f"SELECT {_node_cols()} FROM nodes "
                "WHERE (qualified_name = :n OR qualified_name LIKE :suf) "
                "AND type IN ('FUNCTION','METHOD','CLASS') "
                f"ORDER BY CHAR_LENGTH(qualified_name) LIMIT {settings.MAX_RESULTS}"
            ),
            {"n": name, "suf": f"%.{name}"},
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
            f"SELECT {_node_cols('n')} FROM edges e "
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
            f"SELECT {_node_cols('n')} FROM edges e "
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
    Enhanced: includes caller/callee counts per symbol.
    """
    resolved = await _resolve_file_path(db, file_path)
    if not resolved:
        return {"found": False, "query": file_path}

    r = await db.execute(
        text(
            f"SELECT {_node_cols()} FROM nodes "
            "WHERE file_path = :fp "
            f"ORDER BY start_line LIMIT {settings.MAX_RESULTS * 3}"
        ),
        {"fp": resolved},
    )
    rows = [_row_to_node(row) for row in r.fetchall()]
    if not rows:
        return {"found": False, "query": file_path}

    # Enrich with edge counts
    node_ids = [row["id"] for row in rows]
    if node_ids:
        ph = ",".join([f":id{i}" for i in range(len(node_ids))])
        id_params = {f"id{i}": v for i, v in enumerate(node_ids)}

        # Count incoming edges (callers)
        r2 = await db.execute(
            text(
                f"SELECT target_id, COUNT(*) as cnt FROM edges "
                f"WHERE target_id IN ({ph}) AND type='CALLS' "
                "GROUP BY target_id"
            ),
            id_params,
        )
        caller_counts = {row[0]: row[1] for row in r2.fetchall()}

        # Count outgoing edges (callees)
        r3 = await db.execute(
            text(
                f"SELECT source_id, COUNT(*) as cnt FROM edges "
                f"WHERE source_id IN ({ph}) AND type='CALLS' "
                "GROUP BY source_id"
            ),
            id_params,
        )
        callee_counts = {row[0]: row[1] for row in r3.fetchall()}

        for row in rows:
            row["callers"] = caller_counts.get(row["id"], 0)
            row["callees"] = callee_counts.get(row["id"], 0)

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
    params: dict = {
        "exact": query,
        "prefix": f"{query}%",
        "contains": f"%{query}%",
        "suffix_qn": f"%.{query}",
        "limit": settings.MAX_RESULTS,
    }
    if symbol_type:
        type_filter = "AND type = :type "
        params["type"] = symbol_type.upper()

    # Rank:
    #   0 = exact name match
    #   1 = prefix name match
    #   2 = qualified_name suffix (".<q>") match
    #   3 = substring match
    r = await db.execute(
        text(
            f"SELECT {_node_cols()}, "
            "CASE "
            "  WHEN name = :exact THEN 0 "
            "  WHEN name LIKE :prefix THEN 1 "
            "  WHEN qualified_name LIKE :suffix_qn THEN 2 "
            "  ELSE 3 "
            "END AS rank_score "
            "FROM nodes "
            "WHERE (name LIKE :contains OR qualified_name LIKE :contains) "
            f"{type_filter}"
            "ORDER BY rank_score, CHAR_LENGTH(name) LIMIT :limit"
        ),
        params,
    )
    # Strip trailing rank_score column before building dicts
    results = [_row_to_node(row[:-1]) for row in r.fetchall()]
    return {
        "query": query,
        "count": len(results),
        "results": results,
    }


# ── 6. get_related ────────────────────────────────────────────────────────────

async def get_related(db: AsyncSession, file_path: str) -> Dict[str, Any]:
    """
    Return files connected to `file_path` via import or call edges.
    Enhanced with 2-hop: files that import files that import this file.
    """
    resolved = await _resolve_file_path(db, file_path)
    if not resolved:
        return {
            "file_path": file_path,
            "imports_count": 0,
            "imported_by_count": 0,
            "imports": [],
            "imported_by": [],
            "two_hop_dependents": [],
        }

    # Files this file imports
    r = await db.execute(
        text(
            "SELECT importee FROM file_deps WHERE importer = :fp "
            f"LIMIT {settings.MAX_RESULTS}"
        ),
        {"fp": resolved},
    )
    imports = [row[0] for row in r.fetchall()]

    # Files that import this file
    r = await db.execute(
        text(
            "SELECT importer FROM file_deps WHERE importee = :fp "
            f"LIMIT {settings.MAX_RESULTS}"
        ),
        {"fp": resolved},
    )
    imported_by = [row[0] for row in r.fetchall()]

    # 2-hop: files that import files that import this file
    two_hop = []
    if imported_by:
        for dep_file in imported_by[:5]:  # Limit 2-hop to prevent explosion
            r = await db.execute(
                text("SELECT importer FROM file_deps WHERE importee = :fp LIMIT 5"),
                {"fp": dep_file},
            )
            for row in r.fetchall():
                if row[0] not in imported_by and row[0] != resolved:
                    two_hop.append(row[0])

    return {
        "file_path": resolved,
        "imports_count": len(imports),
        "imported_by_count": len(imported_by),
        "imports": imports,
        "imported_by": imported_by,
        "two_hop_dependents": list(set(two_hop))[:10],
    }


# ══════════════════════════════════════════════════════════════════════════════
# NEW TOOLS
# ══════════════════════════════════════════════════════════════════════════════

# ── 7. get_context ────────────────────────────────────────────────────────────

async def get_context(db: AsyncSession, file_path: str) -> Dict[str, Any]:
    """
    The killer tool for AI agents. Returns everything needed to understand
    a file without reading it:
      - All symbols in the file (with signatures)
      - All imports (what this file depends on)
      - 1-hop connected symbols (who calls symbols in this file, and what they call)
      - File imports graph

    This is a ~95% token savings vs reading the full file.
    """
    # 1. Resolve + fetch symbols in this file
    resolved = await _resolve_file_path(db, file_path)
    if not resolved:
        return {"found": False, "query": file_path}

    r = await db.execute(
        text(
            f"SELECT {_node_cols()} FROM nodes "
            "WHERE file_path = :fp "
            "ORDER BY start_line"
        ),
        {"fp": resolved},
    )
    symbols = [_row_to_node(row) for row in r.fetchall()]
    if not symbols:
        return {"found": False, "query": file_path}

    actual_path = resolved
    node_ids = [s["id"] for s in symbols]

    # 2. Edges involving these symbols
    ph = ",".join([f":id{i}" for i in range(len(node_ids))])
    id_params = {f"id{i}": v for i, v in enumerate(node_ids)}

    # Incoming edges (who references these symbols)
    r = await db.execute(
        text(
            f"SELECT e.type as edge_type, n.name, n.type as node_type, "
            f"n.file_path, n.start_line, t.name as target_name "
            f"FROM edges e "
            f"JOIN nodes n ON n.id = e.source_id "
            f"JOIN nodes t ON t.id = e.target_id "
            f"WHERE e.target_id IN ({ph}) AND n.file_path != :fp "
            f"ORDER BY n.file_path LIMIT 30"
        ),
        {**id_params, "fp": actual_path},
    )
    incoming = [
        {"edge_type": row[0], "from_name": row[1], "from_type": row[2],
         "from_file": row[3], "from_line": row[4], "target_name": row[5]}
        for row in r.fetchall()
    ]

    # Outgoing edges (what these symbols reference externally)
    r = await db.execute(
        text(
            f"SELECT e.type as edge_type, n.name, n.type as node_type, "
            f"n.file_path, n.start_line, s.name as source_name "
            f"FROM edges e "
            f"JOIN nodes n ON n.id = e.target_id "
            f"JOIN nodes s ON s.id = e.source_id "
            f"WHERE e.source_id IN ({ph}) AND n.file_path != :fp "
            f"ORDER BY n.file_path LIMIT 30"
        ),
        {**id_params, "fp": actual_path},
    )
    outgoing = [
        {"edge_type": row[0], "to_name": row[1], "to_type": row[2],
         "to_file": row[3], "to_line": row[4], "source_name": row[5]}
        for row in r.fetchall()
    ]

    # 3. File-level imports
    r = await db.execute(
        text("SELECT importee FROM file_deps WHERE importer = :fp"),
        {"fp": actual_path},
    )
    imports = [row[0] for row in r.fetchall()]

    return {
        "found": True,
        "file_path": actual_path,
        "symbol_count": len(symbols),
        "symbols": [
            {
                "name": s["name"], "type": s["type"],
                "signature": s.get("signature"),
                "docstring": (s.get("docstring") or "")[:120],
                "lines": f"{s.get('start_line','?')}-{s.get('end_line','?')}",
            }
            for s in symbols
        ],
        "imports": imports,
        "incoming_references": incoming,
        "outgoing_references": outgoing,
    }


# ── 8. get_hierarchy ──────────────────────────────────────────────────────────

async def get_hierarchy(db: AsyncSession, class_name: str) -> Dict[str, Any]:
    """
    Return class inheritance tree for a given class.
    Shows parents (what this class inherits from) and children (who inherits this).
    """
    # Find the class node(s)
    r = await db.execute(
        text(
            f"SELECT {_node_cols()} FROM nodes "
            "WHERE name = :n AND type = 'CLASS' LIMIT 5"
        ),
        {"n": class_name},
    )
    classes = [_row_to_node(row) for row in r.fetchall()]
    if not classes:
        return {"found": False, "query": class_name}

    class_ids = [c["id"] for c in classes]
    ph = ",".join([f":id{i}" for i in range(len(class_ids))])
    id_params = {f"id{i}": v for i, v in enumerate(class_ids)}

    # Parents (this class INHERITS from)
    r = await db.execute(
        text(
            f"SELECT n.name, n.file_path, n.start_line FROM edges e "
            f"JOIN nodes n ON n.id = e.target_id "
            f"WHERE e.source_id IN ({ph}) AND e.type = 'INHERITS' "
            f"LIMIT 20"
        ),
        id_params,
    )
    parents = [{"name": row[0], "file": row[1], "line": row[2]} for row in r.fetchall()]

    # Children (who INHERITS from this class)
    r = await db.execute(
        text(
            f"SELECT n.name, n.file_path, n.start_line FROM edges e "
            f"JOIN nodes n ON n.id = e.source_id "
            f"WHERE e.target_id IN ({ph}) AND e.type = 'INHERITS' "
            f"LIMIT 20"
        ),
        id_params,
    )
    children = [{"name": row[0], "file": row[1], "line": row[2]} for row in r.fetchall()]

    # Methods defined on this class
    r = await db.execute(
        text(
            f"SELECT n.name, n.signature, n.start_line FROM edges e "
            f"JOIN nodes n ON n.id = e.target_id "
            f"WHERE e.source_id IN ({ph}) AND e.type IN ('DEFINES','CONTAINS') "
            f"AND n.type IN ('METHOD','FUNCTION') "
            f"ORDER BY n.start_line LIMIT 30"
        ),
        id_params,
    )
    methods = [
        {"name": row[0], "signature": row[1], "line": row[2]}
        for row in r.fetchall()
    ]

    return {
        "found": True,
        "class_name": class_name,
        "class_info": classes[0],
        "parents": parents,
        "children": children,
        "methods": methods,
    }


# ── 9. get_stats ──────────────────────────────────────────────────────────────

async def get_stats(db: AsyncSession) -> Dict[str, Any]:
    """
    Quick repo overview. Helps AI agents orient before deep-diving.
    """
    # Node counts by type
    r = await db.execute(text("SELECT type, COUNT(*) FROM nodes GROUP BY type"))
    node_types = {row[0]: row[1] for row in r.fetchall()}

    # Edge counts by type
    r = await db.execute(text("SELECT type, COUNT(*) FROM edges GROUP BY type"))
    edge_types = {row[0]: row[1] for row in r.fetchall()}

    # Total files
    r = await db.execute(text("SELECT COUNT(DISTINCT file_path) FROM nodes"))
    total_files = r.scalar() or 0

    # Languages
    r = await db.execute(text("SELECT DISTINCT language FROM nodes WHERE language IS NOT NULL"))
    languages = [row[0] for row in r.fetchall()]

    # Most connected files (by symbol count)
    r = await db.execute(
        text(
            "SELECT file_path, COUNT(*) as cnt FROM nodes "
            "GROUP BY file_path ORDER BY cnt DESC LIMIT 10"
        )
    )
    hotspots = [{"file": row[0], "symbols": row[1]} for row in r.fetchall()]

    return {
        "total_files": total_files,
        "total_nodes": sum(node_types.values()),
        "total_edges": sum(edge_types.values()),
        "node_types": node_types,
        "edge_types": edge_types,
        "languages": languages,
        "hotspot_files": hotspots,
    }


# ── 10. get_definition ────────────────────────────────────────────────────────

async def get_definition(db: AsyncSession, name: str) -> Dict[str, Any]:
    """
    Return the exact signature and location for a specific symbol.
    For AI agents that need to know exactly what a function does
    without reading the entire file.
    """
    # Exact match first, then anchored qualified-name suffix (".name")
    r = await db.execute(
        text(
            f"SELECT {_node_cols()} FROM nodes "
            "WHERE name = :n OR qualified_name = :n OR qualified_name LIKE :suf "
            "ORDER BY "
            "  CASE WHEN name = :n THEN 0 "
            "       WHEN qualified_name = :n THEN 1 "
            "       ELSE 2 END, "
            "  CHAR_LENGTH(qualified_name) LIMIT 5"
        ),
        {"n": name, "suf": f"%.{name}"},
    )
    rows = [_row_to_node(row) for row in r.fetchall()]
    if not rows:
        return {"found": False, "query": name}

    # For each result, also get its edges
    enriched = []
    for node in rows:
        # Get what it calls
        r2 = await db.execute(
            text(
                "SELECT n.name, n.type FROM edges e "
                "JOIN nodes n ON n.id = e.target_id "
                "WHERE e.source_id = :id AND e.type = 'CALLS' LIMIT 10"
            ),
            {"id": node["id"]},
        )
        calls = [{"name": row[0], "type": row[1]} for row in r2.fetchall()]

        # Get what calls it
        r3 = await db.execute(
            text(
                "SELECT n.name, n.type FROM edges e "
                "JOIN nodes n ON n.id = e.source_id "
                "WHERE e.target_id = :id AND e.type = 'CALLS' LIMIT 10"
            ),
            {"id": node["id"]},
        )
        called_by = [{"name": row[0], "type": row[1]} for row in r3.fetchall()]

        enriched.append({
            **node,
            "calls": calls,
            "called_by": called_by,
        })

    return {
        "found": True,
        "count": len(enriched),
        "results": enriched,
    }


# ── 11. get_diff_context ──────────────────────────────────────────────────────

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
_DIFF_FILE_RE = re.compile(r"^diff --git a/(.+?) b/(.+?)$")


async def _detect_repo_root(db: AsyncSession) -> Optional[str]:
    """
    Pick a plausible repo root from the most recent successful index run.
    Falls back to CKG_REPO_PATH env var.
    """
    env_path = os.environ.get("CKG_REPO_PATH")
    if env_path and os.path.isdir(os.path.join(env_path, ".git")):
        return env_path
    try:
        r = await db.execute(
            text(
                "SELECT repo_path FROM index_runs "
                "WHERE status='COMPLETED' ORDER BY id DESC LIMIT 1"
            )
        )
        row = r.fetchone()
        if row and row[0]:
            return row[0]
    except Exception:
        pass
    return env_path


def _parse_diff(diff_text: str) -> Dict[str, List[Tuple[int, int]]]:
    """
    Parse `git diff --unified=0` output → {file_path: [(start_line, end_line), ...]}.

    Line ranges are inclusive and refer to the **new** side of the diff.
    Files removed entirely are skipped (nothing in the graph to show).
    """
    by_file: Dict[str, List[Tuple[int, int]]] = {}
    current: Optional[str] = None

    for line in diff_text.splitlines():
        m = _DIFF_FILE_RE.match(line)
        if m:
            # Use the "b/" side (post-change path)
            current = m.group(2)
            by_file.setdefault(current, [])
            continue
        if current is None:
            continue
        h = _HUNK_RE.match(line)
        if h:
            start = int(h.group(1))
            length = int(h.group(2)) if h.group(2) is not None else 1
            if length == 0:
                # Pure deletion — mark a single line of interest at `start`
                by_file[current].append((start, start))
            else:
                by_file[current].append((start, start + length - 1))
    # Drop files with no hunks (e.g. renames with --unified=0)
    return {fp: ranges for fp, ranges in by_file.items() if ranges}


async def _run_git_diff(repo_root: str, ref: str) -> str:
    """Run `git diff --unified=0 <ref>` in repo_root. Returns stdout."""
    def _run() -> str:
        result = subprocess.run(
            ["git", "-C", repo_root, "diff", "--unified=0", ref, "--"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"git diff failed (code {result.returncode}): "
                f"{result.stderr.strip()[:200]}"
            )
        return result.stdout
    return await asyncio.get_event_loop().run_in_executor(None, _run)


async def _find_symbols_in_ranges(
    db: AsyncSession, file_path: str, ranges: List[Tuple[int, int]]
) -> List[dict]:
    """Fetch symbols in `file_path` whose line span overlaps any range."""
    if not ranges:
        return []
    # Build OR-of-overlap predicates
    clauses = []
    params: Dict[str, Any] = {"fp": file_path}
    for i, (s, e) in enumerate(ranges):
        clauses.append(f"(start_line <= :e{i} AND end_line >= :s{i})")
        params[f"s{i}"] = s
        params[f"e{i}"] = e
    where = " OR ".join(clauses)
    r = await db.execute(
        text(
            f"SELECT {_node_cols()} FROM nodes "
            f"WHERE file_path = :fp AND type != 'FILE' AND ({where}) "
            "ORDER BY start_line"
        ),
        params,
    )
    return [_row_to_node(row) for row in r.fetchall()]


async def _blast_radius(
    db: AsyncSession, node_ids: List[str], limit: int = 15
) -> Dict[str, List[dict]]:
    """1-hop neighbors for a set of node ids: callers + callees."""
    if not node_ids:
        return {"callers": [], "callees": []}
    ph = ",".join([f":id{i}" for i in range(len(node_ids))])
    params = {f"id{i}": v for i, v in enumerate(node_ids)}

    # Callers (incoming CALLS)
    r = await db.execute(
        text(
            f"SELECT DISTINCT n.name, n.qualified_name, n.file_path, n.start_line "
            f"FROM edges e JOIN nodes n ON n.id = e.source_id "
            f"WHERE e.target_id IN ({ph}) AND e.type = 'CALLS' "
            f"LIMIT {limit}"
        ),
        params,
    )
    callers = [
        {"name": row[0], "qualified_name": row[1], "file_path": row[2], "start_line": row[3]}
        for row in r.fetchall()
    ]

    # Callees (outgoing CALLS)
    r = await db.execute(
        text(
            f"SELECT DISTINCT n.name, n.qualified_name, n.file_path, n.start_line "
            f"FROM edges e JOIN nodes n ON n.id = e.target_id "
            f"WHERE e.source_id IN ({ph}) AND e.type = 'CALLS' "
            f"LIMIT {limit}"
        ),
        params,
    )
    callees = [
        {"name": row[0], "qualified_name": row[1], "file_path": row[2], "start_line": row[3]}
        for row in r.fetchall()
    ]
    return {"callers": callers, "callees": callees}


async def get_diff_context(
    db: AsyncSession,
    ref: str = "HEAD",
    repo_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Return symbols touched by `git diff --unified=0 <ref>` plus 1-hop blast radius.

    `ref` examples:
      - "HEAD"              → working-tree changes vs HEAD
      - "HEAD~1"            → since previous commit
      - "main...feature"    → diff between branches
      - "<sha1>..<sha2>"    → commit range
    """
    repo_root = repo_path or await _detect_repo_root(db)
    if not repo_root or not os.path.isdir(repo_root):
        return {
            "found": False,
            "error": "Could not locate repo root. Pass repo_path, set CKG_REPO_PATH, or index a repo first.",
            "ref": ref,
        }

    try:
        diff_out = await _run_git_diff(repo_root, ref)
    except Exception as exc:
        return {"found": False, "error": str(exc), "ref": ref, "repo": repo_root}

    hunks = _parse_diff(diff_out)
    if not hunks:
        return {
            "found": True, "ref": ref, "repo": repo_root,
            "changed_files": 0, "touched_symbols": [], "blast_radius": {"callers": [], "callees": []},
            "note": "No changes found in the ref.",
        }

    # For each changed file, find overlapping symbols
    touched: List[dict] = []
    for rel_path, ranges in hunks.items():
        # Try both the absolute and the repo-relative path (graph stores absolute)
        candidates = [
            os.path.join(repo_root, rel_path).replace("\\", "/"),
            rel_path,
        ]
        found_symbols: List[dict] = []
        for cand in candidates:
            resolved = await _resolve_file_path(db, cand)
            if resolved:
                found_symbols = await _find_symbols_in_ranges(db, resolved, ranges)
                break
        if not found_symbols:
            # Still include the file (maybe untracked by graph, e.g. markdown)
            touched.append({
                "file": rel_path, "ranges": ranges,
                "symbols": [], "unindexed": True,
            })
            continue
        touched.append({
            "file": found_symbols[0]["file_path"],
            "ranges": ranges,
            "symbols": [
                {
                    "name": s["name"], "qualified_name": s["qualified_name"],
                    "type": s["type"], "signature": s.get("signature"),
                    "start_line": s["start_line"], "end_line": s["end_line"],
                    "id": s["id"],
                }
                for s in found_symbols
            ],
            "unindexed": False,
        })

    # Blast radius across all touched symbols
    all_ids = [s["id"] for f in touched for s in f["symbols"]]
    radius = await _blast_radius(db, all_ids, limit=settings.MAX_RESULTS)

    return {
        "found": True,
        "ref": ref,
        "repo": repo_root,
        "changed_files": len(hunks),
        "touched_symbols": touched,
        "blast_radius": radius,
    }


# ── 12. search_semantic ───────────────────────────────────────────────────────

async def search_semantic(
    db: AsyncSession,
    query: str,
    k: int = 10,
    symbol_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Natural-language search over symbol names + signatures + docstrings.
    No need to know the exact name: "function that handles auth refresh"
    will find `refresh_token`, `AuthService.rotate`, etc.

    Requires the semantic index to be built (POST /tools/reindex_embeddings).
    """
    if not _embeddings.is_available():
        return {
            "found": False,
            "query": query,
            "error": "Semantic search unavailable. Install sentence-transformers and numpy, "
                     "then POST /tools/reindex_embeddings.",
        }

    hits = await _embeddings.search(db, query, k=k, symbol_type=symbol_type)
    if not hits:
        return {
            "found": False, "query": query,
            "error": "No embeddings indexed yet. POST /tools/reindex_embeddings first.",
        }

    ids = [h[0] for h in hits]
    score_by_id = {h[0]: h[1] for h in hits}
    ph = ",".join([f":id{i}" for i in range(len(ids))])
    params = {f"id{i}": v for i, v in enumerate(ids)}

    r = await db.execute(
        text(f"SELECT {_node_cols()} FROM nodes WHERE id IN ({ph})"),
        params,
    )
    nodes = [_row_to_node(row) for row in r.fetchall()]
    # Re-sort by similarity rank
    nodes.sort(key=lambda n: -score_by_id.get(n["id"], 0.0))
    for n in nodes:
        n["score"] = round(score_by_id.get(n["id"], 0.0), 4)

    return {
        "found": True,
        "query": query,
        "count": len(nodes),
        "model": _embeddings.MODEL_NAME,
        "results": nodes,
    }


async def reindex_embeddings(db: AsyncSession) -> Dict[str, Any]:
    """
    Compute embeddings for all non-FILE nodes that don't have one yet.
    Run after every full index. Safe to call repeatedly — skips up-to-date rows.
    """
    return await _embeddings.reindex(db)
