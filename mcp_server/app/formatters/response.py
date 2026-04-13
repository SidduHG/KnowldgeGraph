"""
Formats resolver output into token-budgeted compact text.
Goal: ≤400 tokens per response so AI agents spend budget on reasoning, not context.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from app.config import settings


def _sig_line(node: dict) -> str:
    parts = [f"[{node['type']}]", node.get("qualified_name") or node["name"]]
    if node.get("signature"):
        parts.append(f"  sig: {node['signature'][:120]}")
    if node.get("docstring"):
        doc = node["docstring"].strip().split("\n")[0][:80]
        parts.append(f"  doc: {doc}")
    loc = f"  @ {node['file_path'].split('/')[-1]}:{node.get('start_line','?')}"
    parts.append(loc)
    return "\n".join(parts)


def _trim(items: List[dict], max_items: int = 10) -> tuple[List[dict], int]:
    trimmed = len(items) - max_items if len(items) > max_items else 0
    return items[:max_items], trimmed


def format_get_function(data: dict) -> str:
    if not data.get("found"):
        return f"No function/class found matching '{data.get('query')}'."
    results, trimmed = _trim(data["results"], 8)
    lines = [f"Found {data['count']} result(s) for '{data.get('query', '')}':"]
    for node in results:
        lines.append("\n" + _sig_line(node))
    if trimmed:
        lines.append(f"\n… and {trimmed} more. Narrow search with get_function(<exact_name>).")
    return "\n".join(lines)


def format_get_callers(data: dict) -> str:
    if not data.get("found"):
        return f"No symbol found named '{data.get('query')}'."
    callers, trimmed = _trim(data["callers"], 10)
    lines = [f"'{data['target']}' is called by {data['caller_count']} function(s):"]
    for c in callers:
        lines.append(f"  • {c.get('qualified_name') or c['name']}  "
                     f"@ {c['file_path'].split('/')[-1]}:{c.get('start_line','?')}")
    if trimmed:
        lines.append(f"  … and {trimmed} more.")
    return "\n".join(lines)


def format_get_callees(data: dict) -> str:
    if not data.get("found"):
        return f"No symbol found named '{data.get('query')}'."
    callees, trimmed = _trim(data["callees"], 10)
    lines = [f"'{data['source']}' calls {data['callee_count']} function(s):"]
    for c in callees:
        lines.append(f"  • {c.get('qualified_name') or c['name']}  "
                     f"@ {c['file_path'].split('/')[-1]}:{c.get('start_line','?')}")
    if trimmed:
        lines.append(f"  … and {trimmed} more.")
    return "\n".join(lines)


def format_get_file_map(data: dict) -> str:
    if not data.get("found"):
        return f"File not in graph: '{data.get('query')}'. Run ckg index first."
    symbols, trimmed = _trim(data["symbols"], 15)
    lines = [f"File: {data['file_path']}  ({data['symbol_count']} symbols)"]
    for s in symbols:
        loc = f"L{s.get('start_line','?')}"
        sig = f"  {s.get('signature','')[:80]}" if s.get("signature") else ""
        lines.append(f"  {loc:6}  [{s['type']:10}]  {s['name']}{sig}")
    if trimmed:
        lines.append(f"  … and {trimmed} more symbols.")
    return "\n".join(lines)


def format_search_symbol(data: dict) -> str:
    results, trimmed = _trim(data["results"], 12)
    lines = [f"Search '{data['query']}': {data['count']} result(s)"]
    for r in results:
        loc = f"{r['file_path'].split('/')[-1]}:{r.get('start_line','?')}"
        sig = f"  ({r.get('signature','')[:60]})" if r.get("signature") else ""
        lines.append(f"  [{r['type']:10}]  {r.get('qualified_name') or r['name']}{sig}  @ {loc}")
    if trimmed:
        lines.append(f"  … and {trimmed} more.")
    return "\n".join(lines)


def format_get_related(data: dict) -> str:
    lines = [f"Related files for: {data['file_path']}"]
    if data["imports"]:
        lines.append(f"\nImports ({data['imports_count']}):")
        for f in data["imports"][:8]:
            lines.append(f"  → {f}")
    if data["imported_by"]:
        lines.append(f"\nImported by ({data['imported_by_count']}):")
        for f in data["imported_by"][:8]:
            lines.append(f"  ← {f}")
    if not data["imports"] and not data["imported_by"]:
        lines.append("  No import relationships found.")
    return "\n".join(lines)


# Dispatch map
FORMATTERS = {
    "get_function":  format_get_function,
    "get_callers":   format_get_callers,
    "get_callees":   format_get_callees,
    "get_file_map":  format_get_file_map,
    "search_symbol": format_search_symbol,
    "get_related":   format_get_related,
}


def format_response(tool: str, data: dict) -> str:
    fn = FORMATTERS.get(tool)
    if fn is None:
        return str(data)
    return fn(data)
