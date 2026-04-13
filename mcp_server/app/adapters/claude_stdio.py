"""
Claude Code MCP adapter — stdio transport.
Run this directly: python -m app.adapters.claude_stdio
Claude Code connects via: claude mcp add ckg python mcp_server/app/adapters/claude_stdio.py
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
            "Use this BEFORE reading a file — saves token usage."
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
            "Get a map of all symbols defined in a file (classes, functions, methods, variables). "
            "Use this to understand a file's structure without reading its full source."
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
            "Get files related to a given file via import/call relationships. "
            "Use this to understand context and blast radius before making changes."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path of the file"},
            },
            "required": ["file_path"],
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
        else:
            data = {"error": f"Unknown tool: {name}"}

    text = format_response(name, data)
    return [types.TextContent(type="text", text=text)]


async def main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
