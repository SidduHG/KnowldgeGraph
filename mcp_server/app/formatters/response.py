"""
Formats resolver output into token-budgeted compact text.
Goal: ≤MAX_TOKENS_PER_RESPONSE per response so AI agents spend budget on
reasoning, not context. Each formatter assembles a line list; the dispatcher
runs a real tiktoken counter and enforces the budget as a HARD cap.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from app.config import settings
from app.formatters.budget import count_tokens, enforce_budget


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


def _short_path(fp: str) -> str:
    """Shorten a file path to the last 3 segments for readability."""
    parts = fp.replace("\\", "/").split("/")
    return "/".join(parts[-3:]) if len(parts) > 3 else fp


# ── Existing formatters ──────────────────────────────────────────────────────

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
                     f"@ {_short_path(c['file_path'])}:{c.get('start_line','?')}")
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
                     f"@ {_short_path(c['file_path'])}:{c.get('start_line','?')}")
    if trimmed:
        lines.append(f"  … and {trimmed} more.")
    return "\n".join(lines)


def format_get_file_map(data: dict) -> str:
    if not data.get("found"):
        return f"File not in graph: '{data.get('query')}'. Run ckg index first."
    symbols, trimmed = _trim(data["symbols"], 15)
    lines = [f"File: {_short_path(data['file_path'])}  ({data['symbol_count']} symbols)"]
    for s in symbols:
        loc = f"L{s.get('start_line','?')}"
        sig = f"  {s.get('signature','')[:80]}" if s.get("signature") else ""
        callers = f"  ↓{s['callers']}" if s.get("callers") else ""
        callees = f"  ↑{s['callees']}" if s.get("callees") else ""
        lines.append(f"  {loc:6}  [{s['type']:10}]  {s['name']}{sig}{callers}{callees}")
    if trimmed:
        lines.append(f"  … and {trimmed} more symbols.")
    return "\n".join(lines)


def format_search_symbol(data: dict) -> str:
    results, trimmed = _trim(data["results"], 12)
    lines = [f"Search '{data['query']}': {data['count']} result(s)"]
    for r in results:
        loc = f"{_short_path(r['file_path'])}:{r.get('start_line','?')}"
        sig = f"  ({r.get('signature','')[:60]})" if r.get("signature") else ""
        lines.append(f"  [{r['type']:10}]  {r.get('qualified_name') or r['name']}{sig}  @ {loc}")
    if trimmed:
        lines.append(f"  … and {trimmed} more.")
    return "\n".join(lines)


def format_get_related(data: dict) -> str:
    lines = [f"Related files for: {_short_path(data['file_path'])}"]
    if data["imports"]:
        lines.append(f"\nImports ({data['imports_count']}):")
        for f in data["imports"][:8]:
            lines.append(f"  → {_short_path(f)}")
    if data["imported_by"]:
        lines.append(f"\nImported by ({data['imported_by_count']}):")
        for f in data["imported_by"][:8]:
            lines.append(f"  ← {_short_path(f)}")
    if data.get("two_hop_dependents"):
        lines.append(f"\n2-hop dependents ({len(data['two_hop_dependents'])}):")
        for f in data["two_hop_dependents"][:5]:
            lines.append(f"  ⟵ {_short_path(f)}")
    if not data["imports"] and not data["imported_by"]:
        lines.append("  No import relationships found.")
    return "\n".join(lines)


# ── New tool formatters ──────────────────────────────────────────────────────

def format_get_context(data: dict) -> str:
    """Format the killer context tool — everything an AI needs about a file."""
    if not data.get("found"):
        return f"File not in graph: '{data.get('query')}'. Run ckg index first."

    lines = [
        f"═══ Context: {_short_path(data['file_path'])} ═══",
        f"Symbols: {data['symbol_count']}  |  Imports: {len(data.get('imports', []))}",
        "",
    ]

    # Symbols
    lines.append("── Symbols ──")
    for s in data["symbols"]:
        sig = f"  {s['signature'][:80]}" if s.get("signature") else ""
        doc = f"  // {s['docstring']}" if s.get("docstring") else ""
        lines.append(f"  [{s['type']:8}] {s['name']}{sig}  L{s['lines']}{doc}")

    # Imports
    if data.get("imports"):
        lines.append(f"\n── Imports ({len(data['imports'])}) ──")
        for imp in data["imports"][:10]:
            lines.append(f"  → {_short_path(imp)}")

    # Incoming references (who uses this file's symbols)
    incoming = data.get("incoming_references", [])
    if incoming:
        lines.append(f"\n── External callers ({len(incoming)}) ──")
        for ref in incoming[:10]:
            lines.append(
                f"  {ref['from_name']} ({ref['from_type']}) "
                f"──{ref['edge_type']}── {ref['target_name']}  "
                f"@ {_short_path(ref['from_file'])}:{ref.get('from_line','?')}"
            )

    # Outgoing references (what this file's symbols reference)
    outgoing = data.get("outgoing_references", [])
    if outgoing:
        lines.append(f"\n── External dependencies ({len(outgoing)}) ──")
        for ref in outgoing[:10]:
            lines.append(
                f"  {ref['source_name']} ──{ref['edge_type']}── "
                f"{ref['to_name']} ({ref['to_type']})  "
                f"@ {_short_path(ref['to_file'])}:{ref.get('to_line','?')}"
            )

    return "\n".join(lines)


def format_get_hierarchy(data: dict) -> str:
    if not data.get("found"):
        return f"No class found named '{data.get('query')}'."

    info = data["class_info"]
    lines = [
        f"═══ Class: {data['class_name']} ═══",
        f"File: {_short_path(info['file_path'])}  L{info.get('start_line','?')}-{info.get('end_line','?')}",
    ]

    if info.get("signature"):
        lines.append(f"Sig: {info['signature'][:120]}")
    if info.get("docstring"):
        lines.append(f"Doc: {info['docstring'][:100]}")

    if data["parents"]:
        lines.append(f"\n── Inherits from ({len(data['parents'])}) ──")
        for p in data["parents"]:
            lines.append(f"  ▲ {p['name']}  @ {_short_path(p['file'])}:{p.get('line','?')}")

    if data["children"]:
        lines.append(f"\n── Inherited by ({len(data['children'])}) ──")
        for c in data["children"]:
            lines.append(f"  ▼ {c['name']}  @ {_short_path(c['file'])}:{c.get('line','?')}")

    if data["methods"]:
        lines.append(f"\n── Methods ({len(data['methods'])}) ──")
        for m in data["methods"]:
            sig = f"  {m['signature'][:80]}" if m.get("signature") else ""
            lines.append(f"  ⚬ {m['name']}{sig}  L{m.get('line','?')}")

    return "\n".join(lines)


def format_get_stats(data: dict) -> str:
    lines = [
        "═══ CKG Repository Overview ═══",
        f"Files: {data['total_files']}  |  Nodes: {data['total_nodes']}  |  Edges: {data['total_edges']}",
        f"Languages: {', '.join(data.get('languages', []))}",
        "",
        "── Node breakdown ──",
    ]
    for ntype, count in sorted(data.get("node_types", {}).items(), key=lambda x: -x[1]):
        lines.append(f"  {ntype:12} {count:>5}")

    lines.append("\n── Edge breakdown ──")
    for etype, count in sorted(data.get("edge_types", {}).items(), key=lambda x: -x[1]):
        lines.append(f"  {etype:12} {count:>5}")

    if data.get("hotspot_files"):
        lines.append("\n── Hotspot files (most symbols) ──")
        for h in data["hotspot_files"][:7]:
            lines.append(f"  {h['symbols']:>3} symbols  {_short_path(h['file'])}")

    return "\n".join(lines)


def format_get_definition(data: dict) -> str:
    if not data.get("found"):
        return f"No symbol found named '{data.get('query')}'."

    lines = [f"Found {data['count']} definition(s):"]
    for node in data["results"]:
        lines.append(f"\n[{node['type']}] {node.get('qualified_name') or node['name']}")
        lines.append(f"  File: {_short_path(node['file_path'])}  "
                     f"L{node.get('start_line','?')}-{node.get('end_line','?')}")
        if node.get("signature"):
            lines.append(f"  Sig: {node['signature'][:140]}")
        if node.get("docstring"):
            lines.append(f"  Doc: {node['docstring'][:120]}")

        if node.get("calls"):
            lines.append(f"  Calls ({len(node['calls'])}):")
            for c in node["calls"][:8]:
                lines.append(f"    → {c['name']} [{c['type']}]")

        if node.get("called_by"):
            lines.append(f"  Called by ({len(node['called_by'])}):")
            for c in node["called_by"][:8]:
                lines.append(f"    ← {c['name']} [{c['type']}]")

    return "\n".join(lines)


def format_search_semantic(data: dict) -> str:
    if not data.get("found"):
        return f"Semantic search failed: {data.get('error', 'unknown')}"
    lines = [f"Semantic search '{data['query']}': {data['count']} hit(s)  (model={data.get('model','?')})"]
    for r in data["results"][:12]:
        score = r.get("score", 0.0)
        loc = f"{_short_path(r['file_path'])}:{r.get('start_line','?')}"
        sig = f"  ({r.get('signature','')[:60]})" if r.get("signature") else ""
        lines.append(
            f"  [{score:.3f}]  [{r['type']:9}]  "
            f"{r.get('qualified_name') or r['name']}{sig}  @ {loc}"
        )
    return "\n".join(lines)


def format_reindex_embeddings(data: dict) -> str:
    if not data.get("ok"):
        return f"Reindex failed: {data.get('error','unknown')}"
    return (
        f"Embeddings reindexed — model={data.get('model')}  "
        f"embedded={data.get('embedded',0)}  total_stale={data.get('total_nodes',0)}"
    )


def format_get_diff_context(data: dict) -> str:
    if not data.get("found"):
        return f"Diff context unavailable: {data.get('error', 'unknown error')} (ref={data.get('ref')})"

    touched = data.get("touched_symbols", [])
    if not touched:
        return f"No changes in ref '{data['ref']}'."

    lines = [
        f"═══ Diff Context: {data['ref']} ═══",
        f"Files changed: {data['changed_files']}  |  Symbols touched: "
        f"{sum(len(f['symbols']) for f in touched)}",
        "",
    ]

    for f in touched[:10]:
        rng_str = ", ".join(f"L{s}-{e}" for s, e in f["ranges"][:5])
        lines.append(f"── {_short_path(f['file'])}  [{rng_str}] ──")
        if f.get("unindexed"):
            lines.append("  (file not in graph — no symbol-level info)")
            continue
        for s in f["symbols"][:10]:
            sig = f"  {s['signature'][:80]}" if s.get("signature") else ""
            lines.append(
                f"  [{s['type']:8}] {s['name']}{sig}  L{s['start_line']}-{s['end_line']}"
            )

    radius = data.get("blast_radius", {})
    callers = radius.get("callers", [])
    callees = radius.get("callees", [])
    if callers:
        lines.append(f"\n── Callers of changed symbols ({len(callers)}) ──")
        for c in callers[:8]:
            lines.append(
                f"  ← {c.get('qualified_name') or c['name']}  "
                f"@ {_short_path(c['file_path'])}:{c.get('start_line','?')}"
            )
    if callees:
        lines.append(f"\n── Callees of changed symbols ({len(callees)}) ──")
        for c in callees[:8]:
            lines.append(
                f"  → {c.get('qualified_name') or c['name']}  "
                f"@ {_short_path(c['file_path'])}:{c.get('start_line','?')}"
            )

    return "\n".join(lines)


# ── Dispatch map ──────────────────────────────────────────────────────────────

FORMATTERS = {
    "get_function":     format_get_function,
    "get_callers":      format_get_callers,
    "get_callees":      format_get_callees,
    "get_file_map":     format_get_file_map,
    "search_symbol":    format_search_symbol,
    "get_related":      format_get_related,
    "get_context":      format_get_context,
    "get_hierarchy":    format_get_hierarchy,
    "get_stats":        format_get_stats,
    "get_definition":   format_get_definition,
    "get_diff_context":     format_get_diff_context,
    "search_semantic":      format_search_semantic,
    "reindex_embeddings":   format_reindex_embeddings,
}


def format_response(tool: str, data: dict, max_tokens: Optional[int] = None) -> str:
    """
    Format `data` via the tool's formatter and enforce the per-response token budget.
    Pass `max_tokens=0` to disable the cap (debug only).
    """
    fn = FORMATTERS.get(tool)
    raw = fn(data) if fn is not None else str(data)

    budget = settings.MAX_TOKENS_PER_RESPONSE if max_tokens is None else max_tokens
    if budget <= 0:
        return raw

    # Fast path: already under budget?
    if count_tokens(raw) <= budget:
        return raw
    # Otherwise re-enforce at line granularity
    return enforce_budget(raw.splitlines(), budget)
