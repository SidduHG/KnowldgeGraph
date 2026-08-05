"""MCP tool resolvers — every tool is a coroutine on the GraphStore.

Tools are organized by intent so they're easy to navigate:
  * ``definition`` — get_function, get_definition, get_hierarchy
  * ``search``     — search_symbol (fuzzy)
  * ``callgraph``  — get_callers, get_callees, call_graph (N-hop)
  * ``usages``     — find_usages
  * ``impact``     — impact_analysis (transitive blast radius)
  * ``subgraph``   — get_subgraph (N-hop arbitrary)
  * ``stats``      — get_stats, list_languages
  * ``ranking``    — rank_symbols (PageRank)
  * ``file``       — get_file_map, get_context, get_related
  * ``path``       — find_path (shortest path between two symbols)
"""
from ckg.mcp.tools.callgraph import call_graph, get_callees, get_callers
from ckg.mcp.tools.definition import get_definition, get_function, get_hierarchy
from ckg.mcp.tools.file import get_context, get_file_map, get_related
from ckg.mcp.tools.impact import impact_analysis
from ckg.mcp.tools.path import find_path
from ckg.mcp.tools.ranking import rank_symbols
from ckg.mcp.tools.search import search_symbol
from ckg.mcp.tools.stats import get_stats, list_languages
from ckg.mcp.tools.subgraph import get_subgraph
from ckg.mcp.tools.usages import find_usages

__all__ = [
    "call_graph",
    "find_path",
    "find_usages",
    "get_callees",
    "get_callers",
    "get_context",
    "get_definition",
    "get_file_map",
    "get_function",
    "get_hierarchy",
    "get_related",
    "get_stats",
    "get_subgraph",
    "impact_analysis",
    "list_languages",
    "rank_symbols",
    "search_symbol",
]
