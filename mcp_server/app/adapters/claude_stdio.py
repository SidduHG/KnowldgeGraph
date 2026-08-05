"""
Claude Code MCP adapter — stdio transport.
Run this directly: python -m app.adapters.claude_stdio
Claude Code connects via: claude mcp add ckg python mcp_server/app/adapters/claude_stdio.py

10 Tools:
  get_function    — Full details of a function/method/class by name
  get_callers     — All functions that call a given function
  get_callees     — All functions called by a given function
  get_file_map    — All symbols defined in a file (with connection counts)
  search_symbol   — Fuzzy search across all symbol names
  get_related     — Files connected via import/call edges (2-hop)
  get_context     — 1-hop context: everything needed to understand a file
  get_hierarchy   — Class inheritance tree
  get_stats       — Quick repo overview for orientation
  get_definition  — Exact definition + call graph for a symbol
"""
from __future__ import annotations
import asyncio
import logging

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from app.database import db_session
from app.tools import resolvers
from app.formatters.response import format_response

logger = logging.getLogger(__name__)

server = Server("ckg")

TOOL_DEFINITIONS = [
    types.Tool(
        name="get_function",
        description=(
            "Get full details of a function, method, or class by name. "
            "Returns signature, docstring, file location, and line range. "
            "Use this BEFORE reading a file — saves ~95% token usage."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Function or class name (exact or partial)"},
            },
            "required": ["name"],
        },
    ),
    types.Tool(
        name="get_callers",
        description=(
            "Find all functions that call a given function. "
            "Use this to understand impact before modifying a function."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the function being called"},
            },
            "required": ["name"],
        },
    ),
    types.Tool(
        name="get_callees",
        description="Find all functions called by a given function.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the calling function"},
            },
            "required": ["name"],
        },
    ),
    types.Tool(
        name="get_file_map",
        description=(
            "Get a map of all symbols defined in a file (classes, functions, methods, variables) "
            "with caller/callee counts. Use this to understand a file's structure without reading it."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute or relative file path"},
            },
            "required": ["file_path"],
        },
    ),
    types.Tool(
        name="search_symbol",
        description=(
            "Fuzzy search for any symbol across the entire codebase by name. "
            "Use this when you need to find where something is defined or used."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Symbol name to search"},
                "type": {
                    "type": "string",
                    "enum": ["FUNCTION", "CLASS", "METHOD", "VARIABLE", "TYPE"],
                    "description": "Optional: filter by symbol type",
                },
            },
            "required": ["query"],
        },
    ),
    types.Tool(
        name="get_related",
        description=(
            "Get files related to a given file via import/call relationships (1-hop and 2-hop). "
            "Use this to understand blast radius before making changes."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path of the file"},
            },
            "required": ["file_path"],
        },
    ),
    types.Tool(
        name="get_context",
        description=(
            "THE PRIMARY TOOL — Get everything needed to understand a file without reading it: "
            "all symbols (with signatures), imports, incoming/outgoing references. "
            "~95% token reduction vs reading the full file. Use this FIRST."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "File path to get context for"},
            },
            "required": ["file_path"],
        },
    ),
    types.Tool(
        name="get_hierarchy",
        description=(
            "Get the class inheritance tree: parents, children, and methods. "
            "Use for understanding OOP relationships."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "class_name": {"type": "string", "description": "Name of the class"},
            },
            "required": ["class_name"],
        },
    ),
    types.Tool(
        name="get_stats",
        description=(
            "Get a quick overview of the entire repository: file count, node/edge breakdown, "
            "languages, and hotspot files. Use this FIRST to orient yourself."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    types.Tool(
        name="get_definition",
        description=(
            "Get the exact definition of a symbol with its full call graph (what it calls, "
            "what calls it). Use when you need surgical precision on a specific symbol."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Symbol name (exact)"},
            },
            "required": ["name"],
        },
    ),
    types.Tool(
        name="search_semantic",
        description=(
            "Natural-language symbol search — find a function by what it does, "
            "not what it's named. E.g. 'function that refreshes auth tokens' → "
            "ranks `rotate_access_token`, `AuthService.refresh` etc. "
            "Requires embeddings to have been indexed (reindex_embeddings)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Plain-English query"},
                "k":     {"type": "integer", "description": "Top-k results (default 10)"},
                "type":  {
                    "type": "string",
                    "enum": ["FUNCTION", "CLASS", "METHOD", "VARIABLE", "TYPE"],
                    "description": "Optional: filter by type",
                },
            },
            "required": ["query"],
        },
    ),
    types.Tool(
        name="reindex_embeddings",
        description=(
            "Compute semantic embeddings for every node that doesn't have one. "
            "Run this once after a full index to enable search_semantic."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="get_diff_context",
        description=(
            "PR-review superpower — given a git ref (HEAD, HEAD~1, main...feature, sha1..sha2), "
            "return ONLY the symbols whose lines changed plus 1-hop blast radius (callers/callees). "
            "Drop-in replacement for pasting a raw diff; ~90%+ token savings."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "ref":       {"type": "string", "description": "Git ref or range. Default: HEAD"},
                "repo_path": {"type": "string", "description": "Optional repo root override"},
            },
            "required": [],
        },
    ),
]


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return TOOL_DEFINITIONS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    async with db_session() as session:
        if name == "get_function":
            data = await resolvers.get_function(session, arguments["name"])
        elif name == "get_callers":
            data = await resolvers.get_callers(session, arguments["name"])
        elif name == "get_callees":
            data = await resolvers.get_callees(session, arguments["name"])
        elif name == "get_file_map":
            data = await resolvers.get_file_map(session, arguments["file_path"])
        elif name == "search_symbol":
            data = await resolvers.search_symbol(
                session, arguments["query"], arguments.get("type")
            )
        elif name == "get_related":
            data = await resolvers.get_related(session, arguments["file_path"])
        elif name == "get_context":
            data = await resolvers.get_context(session, arguments["file_path"])
        elif name == "get_hierarchy":
            data = await resolvers.get_hierarchy(session, arguments["class_name"])
        elif name == "get_stats":
            data = await resolvers.get_stats(session)
        elif name == "get_definition":
            data = await resolvers.get_definition(session, arguments["name"])
        elif name == "get_diff_context":
            data = await resolvers.get_diff_context(
                session,
                ref=arguments.get("ref", "HEAD"),
                repo_path=arguments.get("repo_path"),
            )
        elif name == "search_semantic":
            data = await resolvers.search_semantic(
                session,
                arguments["query"],
                k=arguments.get("k", 10),
                symbol_type=arguments.get("type"),
            )
        elif name == "reindex_embeddings":
            data = await resolvers.reindex_embeddings(session)
        else:
            data = {"error": f"Unknown tool: {name}"}

    text = format_response(name, data)
    return [types.TextContent(type="text", text=text)]


async def main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
