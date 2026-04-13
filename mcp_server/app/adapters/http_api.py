"""
HTTP adapter — REST JSON API for Codex, Gemini, Cursor.

Each agent integration:

  CODEX    → add tool definitions to tools[] in your OpenAI API call
             pointing at POST /tools/{tool_name}

  GEMINI   → use function declarations pointing at POST /tools/{tool_name}
             or use /openai/tools for OpenAI-compatible format

  CURSOR   → add to .cursor/mcp.json using http transport

  Any      → GET /config to get ready-made tool definitions for your agent
"""
from __future__ import annotations
import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.tools import resolvers
from app.formatters.response import format_response

logger = logging.getLogger(__name__)

app = FastAPI(
    title="CKG MCP Server",
    description="Code Knowledge Graph — AI agent tool API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ─────────────────────────────────────────────────

class ToolRequest(BaseModel):
    name:      Optional[str] = None
    file_path: Optional[str] = None
    query:     Optional[str] = None
    type:      Optional[str] = None


class ToolResponse(BaseModel):
    tool: str
    raw:  Dict[str, Any]
    text: str            # token-budgeted formatted text
    tokens_est: int      # rough token estimate


def _wrap(tool: str, data: dict) -> ToolResponse:
    text = format_response(tool, data)
    return ToolResponse(
        tool=tool, raw=data, text=text,
        tokens_est=len(text.split()) * 4 // 3,
    )


# ── Tool endpoints ─────────────────────────────────────────────────────────────

@app.post("/tools/get_function", response_model=ToolResponse)
async def tool_get_function(req: ToolRequest, db: AsyncSession = Depends(get_db)):
    if not req.name:
        raise HTTPException(400, "name is required")
    data = await resolvers.get_function(db, req.name)
    return _wrap("get_function", data)


@app.post("/tools/get_callers", response_model=ToolResponse)
async def tool_get_callers(req: ToolRequest, db: AsyncSession = Depends(get_db)):
    if not req.name:
        raise HTTPException(400, "name is required")
    data = await resolvers.get_callers(db, req.name)
    return _wrap("get_callers", data)


@app.post("/tools/get_callees", response_model=ToolResponse)
async def tool_get_callees(req: ToolRequest, db: AsyncSession = Depends(get_db)):
    if not req.name:
        raise HTTPException(400, "name is required")
    data = await resolvers.get_callees(db, req.name)
    return _wrap("get_callees", data)


@app.post("/tools/get_file_map", response_model=ToolResponse)
async def tool_get_file_map(req: ToolRequest, db: AsyncSession = Depends(get_db)):
    if not req.file_path:
        raise HTTPException(400, "file_path is required")
    data = await resolvers.get_file_map(db, req.file_path)
    return _wrap("get_file_map", data)


@app.post("/tools/search_symbol", response_model=ToolResponse)
async def tool_search_symbol(req: ToolRequest, db: AsyncSession = Depends(get_db)):
    if not req.query:
        raise HTTPException(400, "query is required")
    data = await resolvers.search_symbol(db, req.query, req.type)
    return _wrap("search_symbol", data)


@app.post("/tools/get_related", response_model=ToolResponse)
async def tool_get_related(req: ToolRequest, db: AsyncSession = Depends(get_db)):
    if not req.file_path:
        raise HTTPException(400, "file_path is required")
    data = await resolvers.get_related(db, req.file_path)
    return _wrap("get_related", data)


# ── Config / discovery endpoints ──────────────────────────────────────────────

@app.get("/config")
async def get_config(agent: str = "auto"):
    """
    Returns ready-made tool definitions for the requested agent type.
    agent: claude | codex | gemini | cursor | auto
    """
    base_url = f"http://{settings.HOST}:{settings.PORT}"

    # Tool descriptions shared across all formats
    tools_meta = [
        {
            "name": "get_function",
            "description": "Get signature, docstring, and location of a function/class by name. Use before reading files.",
            "params": {"name": {"type": "string", "description": "Function or class name"}},
            "required": ["name"],
        },
        {
            "name": "get_callers",
            "description": "Find all functions that call a given function. Use before modifying a function.",
            "params": {"name": {"type": "string", "description": "Function name"}},
            "required": ["name"],
        },
        {
            "name": "get_callees",
            "description": "Find all functions called by a given function.",
            "params": {"name": {"type": "string", "description": "Function name"}},
            "required": ["name"],
        },
        {
            "name": "get_file_map",
            "description": "List all symbols in a file without reading its full source.",
            "params": {"file_path": {"type": "string", "description": "File path"}},
            "required": ["file_path"],
        },
        {
            "name": "search_symbol",
            "description": "Fuzzy-search any symbol across the entire codebase.",
            "params": {
                "query": {"type": "string", "description": "Search query"},
                "type": {"type": "string", "enum": ["FUNCTION","CLASS","METHOD","VARIABLE","TYPE"],
                         "description": "Optional type filter"},
            },
            "required": ["query"],
        },
        {
            "name": "get_related",
            "description": "Get files related to a file via imports/calls. Shows blast radius.",
            "params": {"file_path": {"type": "string", "description": "File path"}},
            "required": ["file_path"],
        },
    ]

    if agent in ("codex", "auto"):
        # OpenAI function-calling format
        return {
            "agent": "codex",
            "format": "openai_tools",
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": {
                            "type": "object",
                            "properties": t["params"],
                            "required": t["required"],
                        },
                    },
                    "endpoint": f"{base_url}/tools/{t['name']}",
                }
                for t in tools_meta
            ],
            "usage_note": (
                "Add these to your tools[] array. When OpenAI calls a tool, "
                f"POST to {base_url}/tools/<tool_name> with the arguments JSON. "
                "Return the 'text' field as the tool result."
            ),
        }

    if agent == "gemini":
        return {
            "agent": "gemini",
            "format": "google_function_declarations",
            "function_declarations": [
                {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            k: {"type": "STRING", "description": v["description"]}
                            for k, v in t["params"].items()
                        },
                        "required": t["required"],
                    },
                }
                for t in tools_meta
            ],
            "base_url": base_url,
            "usage_note": (
                "Use these as function_declarations in your GenerativeModel tools param. "
                f"When Gemini calls a function, POST to {base_url}/tools/<name>."
            ),
        }

    if agent == "cursor":
        return {
            "agent": "cursor",
            "format": "cursor_mcp_json",
            "mcp_config": {
                "mcpServers": {
                    "ckg": {
                        "url": f"{base_url}/mcp",
                        "transport": "http",
                    }
                }
            },
            "file": ".cursor/mcp.json",
            "usage_note": "Add the mcpServers block to your .cursor/mcp.json file.",
        }

    if agent == "claude":
        return {
            "agent": "claude",
            "format": "claude_mcp_stdio",
            "command": "python mcp_server/app/adapters/claude_stdio.py",
            "claude_code_command": "claude mcp add ckg python mcp_server/app/adapters/claude_stdio.py",
            "usage_note": "Run the claude_code_command once. Claude Code will use the tools automatically.",
        }

    return {"error": f"Unknown agent: {agent}. Use: claude | codex | gemini | cursor | auto"}


@app.get("/health")
async def health():
    return {"ok": True, "version": "1.0.0", "mode": settings.MODE}
