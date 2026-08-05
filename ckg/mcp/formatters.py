"""Token-budgeted formatters for every MCP tool.

Each formatter renders the raw resolver dict into compact text. The dispatcher
runs ``count_tokens`` and falls back to ``enforce_budget`` if the rendered
string exceeds ``settings.MAX_TOKENS_PER_RESPONSE``.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from ckg.config import settings
from ckg.mcp.budget import count_tokens, enforce_budget


def _short(fp: str) -> str:
    parts = fp.replace("\\", "/").split("/")
    return "/".join(parts[-3:]) if len(parts) > 3 else fp


def _trim(items: list, n: int) -> tuple[list, int]:
    return (items[:n], max(0, len(items) - n))


# ── Existing tools ───────────────────────────────────────────────────────────
def fmt_get_function(d: Dict[str, Any]) -> str:
    if not d.get("found"):
        return f"No function/class found matching '{d.get('query')}'."
    items, more = _trim(d["results"], 8)
    lines = [f"Found {d['count']} result(s) for '{d['query']}':"]
    for r in items:
        loc = f"{_short(r['file_path'])}:{r.get('start_line','?')}"
        sig = f"  sig: {r['signature'][:120]}" if r.get("signature") else ""
        doc = f"  doc: {r['docstring'].splitlines()[0][:80]}" if r.get("docstring") else ""
        lines.append(f"\n[{r['type']}] {r.get('qualified_name') or r['name']}{sig}{doc}\n  @ {loc}")
    if more:
        lines.append(f"\n… and {more} more.")
    return "\n".join(lines)


def fmt_get_definition(d: Dict[str, Any]) -> str:
    if not d.get("found"):
        return f"No symbol named '{d.get('query')}'."
    lines = [f"Found {d['count']} definition(s):"]
    for r in d["results"]:
        loc = f"{_short(r['file_path'])} L{r.get('start_line','?')}-{r.get('end_line','?')}"
        lines.append(f"\n[{r['type']}] {r.get('qualified_name') or r['name']}")
        lines.append(f"  File: {loc}")
        if r.get("signature"):
            lines.append(f"  Sig: {r['signature'][:140]}")
        if r.get("calls"):
            lines.append(f"  Calls ({len(r['calls'])}): " + ", ".join(c["name"] for c in r["calls"][:8]))
        if r.get("called_by"):
            lines.append(f"  Called by ({len(r['called_by'])}): " + ", ".join(c["name"] for c in r["called_by"][:8]))
    return "\n".join(lines)


def fmt_search_symbol(d: Dict[str, Any]) -> str:
    items, more = _trim(d["results"], 12)
    lines = [f"Search '{d['query']}': {d['count']} result(s)"]
    for r in items:
        loc = f"{_short(r['file_path'])}:{r.get('start_line','?')}"
        sig = f"  ({r['signature'][:60]})" if r.get("signature") else ""
        lines.append(f"  [{r['type']:9}] {r.get('qualified_name') or r['name']}{sig}  @ {loc}")
    if more:
        lines.append(f"  … and {more} more.")
    return "\n".join(lines)


def fmt_get_callers(d: Dict[str, Any]) -> str:
    if not d.get("found"):
        return f"No symbol named '{d.get('query')}'."
    items, more = _trim(d["callers"], 10)
    lines = [f"'{d['target']}' is called by {d['caller_count']} function(s):"]
    for c in items:
        lines.append(f"  • {c.get('qualified_name') or c['name']}  @ {_short(c['file_path'])}:{c.get('start_line','?')}")
    if more:
        lines.append(f"  … and {more} more.")
    return "\n".join(lines)


def fmt_get_callees(d: Dict[str, Any]) -> str:
    if not d.get("found"):
        return f"No symbol named '{d.get('query')}'."
    items, more = _trim(d["callees"], 10)
    lines = [f"'{d['source']}' calls {d['callee_count']} function(s):"]
    for c in items:
        lines.append(f"  • {c.get('qualified_name') or c['name']}  @ {_short(c['file_path'])}:{c.get('start_line','?')}")
    if more:
        lines.append(f"  … and {more} more.")
    return "\n".join(lines)


def fmt_get_file_map(d: Dict[str, Any]) -> str:
    if not d.get("found"):
        return f"File not in graph: '{d['file_path']}'."
    items, more = _trim(d["symbols"], 15)
    lines = [f"File: {_short(d['file_path'])}  ({d['symbol_count']} symbols)"]
    for s in items:
        loc = f"L{s.get('start_line','?')}"
        sig = f"  {s['signature'][:80]}" if s.get("signature") else ""
        lines.append(f"  {loc:6}  [{s['type']:10}]  {s['name']}{sig}  ↓{s.get('callers',0)} ↑{s.get('callees',0)}")
    if more:
        lines.append(f"  … and {more} more.")
    return "\n".join(lines)


def fmt_get_context(d: Dict[str, Any]) -> str:
    if not d.get("found"):
        return f"File not in graph: '{d['file_path']}'."
    lines = [
        f"═══ Context: {_short(d['file_path'])} ═══",
        f"Symbols: {d['symbol_count']}  |  Imports: {len(d.get('imports', []))}",
        "",
        "── Symbols ──",
    ]
    for s in d["symbols"]:
        sig = f"  {s['signature'][:80]}" if s.get("signature") else ""
        lines.append(f"  [{s['type']:8}] {s['name']}{sig}  L{s['lines']}")
    if d.get("imports"):
        lines.append(f"\n── Imports ({len(d['imports'])}) ──")
        for imp in d["imports"][:10]:
            lines.append(f"  → {_short(imp)}")
    if d.get("incoming_references"):
        lines.append(f"\n── External callers ({len(d['incoming_references'])}) ──")
        for r in d["incoming_references"][:8]:
            lines.append(f"  {r['from_name']} → {r['target_name']}  @ {_short(r['from_file'])}:{r.get('from_line','?')}")
    return "\n".join(lines)


def fmt_get_related(d: Dict[str, Any]) -> str:
    lines = [f"Related files for: {_short(d['file_path'])}"]
    if d["imports"]:
        lines.append(f"\nImports ({d['imports_count']}):")
        for f in d["imports"][:8]:
            lines.append(f"  → {_short(f)}")
    if d["imported_by"]:
        lines.append(f"\nImported by ({d['imported_by_count']}):")
        for f in d["imported_by"][:8]:
            lines.append(f"  ← {_short(f)}")
    if d.get("two_hop_dependents"):
        lines.append(f"\n2-hop dependents ({len(d['two_hop_dependents'])}):")
        for f in d["two_hop_dependents"][:5]:
            lines.append(f"  ⟵ {_short(f)}")
    return "\n".join(lines)


def fmt_get_hierarchy(d: Dict[str, Any]) -> str:
    if not d.get("found"):
        return f"No class found named '{d.get('query')}'."
    info = d["class_info"]
    lines = [
        f"═══ Class: {d['class_name']} ═══",
        f"File: {_short(info['file_path'])}  L{info.get('start_line','?')}-{info.get('end_line','?')}",
    ]
    if d["parents"]:
        lines.append(f"\nInherits from ({len(d['parents'])}):")
        for p in d["parents"]:
            lines.append(f"  ▲ {p['name']}  @ {_short(p['file'])}:{p.get('line','?')}")
    if d["children"]:
        lines.append(f"\nInherited by ({len(d['children'])}):")
        for c in d["children"]:
            lines.append(f"  ▼ {c['name']}  @ {_short(c['file'])}:{c.get('line','?')}")
    if d["methods"]:
        lines.append(f"\nMethods ({len(d['methods'])}):")
        for m in d["methods"]:
            lines.append(f"  ⚬ {m['name']}{m.get('signature','') and ' '+m['signature'][:80]}  L{m.get('line','?')}")
    return "\n".join(lines)


def fmt_get_stats(d: Dict[str, Any]) -> str:
    lines = [
        "═══ CKG Repository Overview ═══",
        f"Files: {d['total_files']}  |  Nodes: {d['total_nodes']}  |  Edges: {d['total_edges']}",
        f"Languages: {', '.join(d.get('languages', []))}",
        "",
        "── Node breakdown ──",
    ]
    for k, v in sorted(d.get("node_types", {}).items(), key=lambda x: -x[1]):
        lines.append(f"  {k:12} {v:>5}")
    lines.append("\n── Edge breakdown ──")
    for k, v in sorted(d.get("edge_types", {}).items(), key=lambda x: -x[1]):
        lines.append(f"  {k:12} {v:>5}")
    if d.get("hotspot_files"):
        lines.append("\n── Hotspots ──")
        for h in d["hotspot_files"][:7]:
            lines.append(f"  {h['symbols']:>3}  {_short(h['file'])}")
    return "\n".join(lines)


def fmt_list_languages(d: Dict[str, Any]) -> str:
    return (
        "Registered parsers: " + ", ".join(d["registered_parsers"]) +
        "\nLanguages in graph: " + ", ".join(d["languages_in_graph"] or ["—"])
    )


# ── New tools ────────────────────────────────────────────────────────────────
def fmt_find_usages(d: Dict[str, Any]) -> str:
    if not d.get("found"):
        return f"No symbol named '{d.get('query')}'."
    items, more = _trim(d["usages"], 12)
    lines = [f"'{d['target']}' is used in {d['usage_count']} place(s):"]
    for u in items:
        lines.append(
            f"  [{u['edge_type']:8}] {u['user_name']} ({u['user_type']})  "
            f"@ {_short(u['file_path'])}:{u.get('line','?')}"
        )
    if more:
        lines.append(f"  … and {more} more.")
    return "\n".join(lines)


def fmt_call_graph(d: Dict[str, Any]) -> str:
    if not d.get("found"):
        return f"No symbol named '{d.get('query')}'."
    lines = [
        f"═══ Call graph: {d['root']} (depth={d['depth']}, dir={d['direction']}) ═══",
        f"Edges: {d['edge_count']}",
        "",
    ]
    for e in d["edges"][:20]:
        arrow = "→" if e["direction"] == "out" else "←"
        lines.append(f"  hop{e['hop']}  {arrow}  {e['name']}  @ {_short(e['file_path'])}:{e.get('start_line','?')}")
    if len(d["edges"]) > 20:
        lines.append(f"  … and {len(d['edges']) - 20} more.")
    return "\n".join(lines)


def fmt_impact_analysis(d: Dict[str, Any]) -> str:
    if not d.get("found"):
        return f"No symbol named '{d.get('query')}'."
    seed = d["seed"]
    lines = [
        f"═══ Impact analysis: {seed['name']} ═══",
        f"Seed: {_short(seed['file_path'])}  type={seed['type']}",
        f"Impacted symbols: {d['impacted_symbol_count']}  |  files: {d['impacted_file_count']}",
        "",
    ]
    for layer in d["by_hop"][:3]:
        lines.append(f"── hop {layer['hop']}: {layer['count']} user(s) ──")
        for u in layer["users"][:6]:
            lines.append(f"  [{u['edge_type']:8}] {u['name']} ({u['type']})  @ {_short(u['file_path'])}:{u.get('line','?')}")
    if d.get("impacted_files"):
        lines.append("\n── Files needing review ──")
        for f in d["impacted_files"][:10]:
            lines.append(f"  • {_short(f)}")
    return "\n".join(lines)


def fmt_get_subgraph(d: Dict[str, Any]) -> str:
    if not d.get("found"):
        return f"No symbol named '{d.get('query')}'."
    lines = [
        f"═══ Subgraph: {d['seed']} (depth={d['depth']}) ═══",
        f"Nodes: {d['node_count']}  |  Edges: {d['edge_count']}",
        "",
    ]
    for n in d["nodes"][:15]:
        lines.append(f"  • [{n['type']:8}] {n['name']}  @ {_short(n['file_path'])}")
    if d["node_count"] > 15:
        lines.append(f"  … and {d['node_count'] - 15} more.")
    return "\n".join(lines)


def fmt_rank_symbols(d: Dict[str, Any]) -> str:
    if not d.get("found"):
        return "No ranking available — run an index first."
    lines = [f"Top {d['k']} symbols by PageRank:"]
    for r in d["results"]:
        lines.append(
            f"  {r['score']:.4f}  [{r['type']:9}] "
            f"{r.get('qualified_name') or r['name']}  @ {_short(r['file_path'])}:{r.get('start_line','?')}"
        )
    return "\n".join(lines)


def fmt_find_path(d: Dict[str, Any]) -> str:
    if not d.get("found"):
        return f"No path from '{d.get('source')}' to '{d.get('target')}' (within hop limit)."
    lines = [f"Path ({d['hops']} hops): {d['source']} → {d['target']}"]
    for i, n in enumerate(d["path"]):
        prefix = "  " + (" " * i) + ("→ " if i else "")
        lines.append(f"{prefix}{n['name']} [{n['type']}]  @ {_short(n['file_path'])}")
    return "\n".join(lines)


# ── Dispatch ─────────────────────────────────────────────────────────────────
FORMATTERS: Dict[str, Callable[[Dict[str, Any]], str]] = {
    "get_function": fmt_get_function,
    "get_definition": fmt_get_definition,
    "search_symbol": fmt_search_symbol,
    "get_callers": fmt_get_callers,
    "get_callees": fmt_get_callees,
    "get_file_map": fmt_get_file_map,
    "get_context": fmt_get_context,
    "get_related": fmt_get_related,
    "get_hierarchy": fmt_get_hierarchy,
    "get_stats": fmt_get_stats,
    "list_languages": fmt_list_languages,
    "find_usages": fmt_find_usages,
    "call_graph": fmt_call_graph,
    "impact_analysis": fmt_impact_analysis,
    "get_subgraph": fmt_get_subgraph,
    "rank_symbols": fmt_rank_symbols,
    "find_path": fmt_find_path,
}


def format_response(tool: str, data: Dict[str, Any], max_tokens: Optional[int] = None) -> str:
    """Format a resolver result + enforce the per-response token budget."""
    fn = FORMATTERS.get(tool)
    raw = fn(data) if fn else str(data)
    budget = settings.MAX_TOKENS_PER_RESPONSE if max_tokens is None else max_tokens
    if budget <= 0:
        return raw
    if count_tokens(raw) <= budget:
        return raw
    return enforce_budget(raw.splitlines(), budget)
