"""MCP stdio adapter — for Claude Code / any MCP-stdio client.

Wraps the same tool resolvers used by the HTTP server. Run with::

    python -m ckg.mcp.stdio
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict

from ckg.config import settings
from ckg.mcp import tools
from ckg.mcp.formatters import format_response
from ckg.observability import get_logger, setup_logging
from ckg.store.base import GraphStore
from ckg.store.factory import open_store

logger = get_logger(__name__)


_TOOL_HANDLERS: Dict[str, Any] = {
    "get_function":     lambda s, a: tools.get_function(s, a["name"]),
    "get_definition":   lambda s, a: tools.get_definition(s, a["name"]),
    "search_symbol":    lambda s, a: tools.search_symbol(s, a["query"], a.get("type")),
    "get_callers":      lambda s, a: tools.get_callers(s, a["name"]),
    "get_callees":      lambda s, a: tools.get_callees(s, a["name"]),
    "call_graph":       lambda s, a: tools.call_graph(s, a["name"], depth=a.get("depth", 2), direction=a.get("direction", "both")),
    "find_usages":      lambda s, a: tools.find_usages(s, a["name"]),
    "impact_analysis":  lambda s, a: tools.impact_analysis(s, a["name"], max_depth=a.get("max_depth", 3)),
    "get_subgraph":     lambda s, a: tools.get_subgraph(s, a["name"], depth=a.get("depth", 2), edge_types=a.get("edge_types"), direction=a.get("direction", "both")),
    "find_path":        lambda s, a: tools.find_path(s, a["source"], a["target"], max_hops=a.get("max_hops", 6)),
    "rank_symbols":     lambda s, a: tools.rank_symbols(s, k=a.get("k", 20)),
    "get_file_map":     lambda s, a: tools.get_file_map(s, a["file_path"]),
    "get_context":      lambda s, a: tools.get_context(s, a["file_path"]),
    "get_related":      lambda s, a: tools.get_related(s, a["file_path"]),
    "get_hierarchy":    lambda s, a: tools.get_hierarchy(s, a["class_name"]),
    "get_stats":        lambda s, a: tools.get_stats(s),
    "list_languages":   lambda s, a: tools.list_languages(s),
}


async def _run() -> None:
    setup_logging(settings.DEBUG, fmt=settings.LOG_FORMAT)
    store: GraphStore = await open_store()
    try:
        # Expose the resolver dict via the official ``mcp`` Python SDK if installed.
        try:
            from mcp.server import Server  # type: ignore
            from mcp.server.stdio import stdio_server  # type: ignore
        except ImportError:
            logger.error("mcp SDK not installed — `pip install mcp`")
            return

        server = Server("ckg")

        @server.list_tools()  # type: ignore
        async def _list_tools():
            return [
                {"name": name, "description": f"CKG tool: {name}"}
                for name in _TOOL_HANDLERS
            ]

        @server.call_tool()  # type: ignore
        async def _call_tool(name: str, arguments: dict):
            handler = _TOOL_HANDLERS.get(name)
            if handler is None:
                return [{"type": "text", "text": f"unknown tool: {name}"}]
            data = await handler(store, arguments or {})
            text = format_response(name, data)
            return [{"type": "text", "text": text}]

        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
    finally:
        await store.close()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
