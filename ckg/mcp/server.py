"""Unified MCP HTTP server.

Exposes every tool under ``POST /tools/<tool_name>`` with a uniform
``ToolRequest`` body, plus discovery (`GET /config`), health, and a
Prometheus ``/metrics`` endpoint.

The server holds **one** ``GraphStore`` instance for the process — created
in the FastAPI ``lifespan`` and injected via dependency override.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from ckg.__version__ import __version__
from ckg.config import settings
from ckg.mcp import tools
from ckg.mcp.budget import count_tokens
from ckg.mcp.formatters import format_response
from ckg.observability import counter, get_logger, registry as metrics_registry, setup_logging
from ckg.store.base import GraphStore
from ckg.store.factory import open_store

logger = get_logger(__name__)
_TOOL_CALLS = counter("ckg_mcp_tool_calls_total", "MCP tool calls", labels={"tool": "*"})


# ── Request / response models ────────────────────────────────────────────────
class ToolRequest(BaseModel):
    name: Optional[str] = None
    file_path: Optional[str] = None
    query: Optional[str] = None
    type: Optional[str] = None
    class_name: Optional[str] = None
    source: Optional[str] = None
    target: Optional[str] = None
    depth: Optional[int] = None
    max_depth: Optional[int] = None
    max_hops: Optional[int] = None
    edge_types: Optional[List[str]] = None
    direction: Optional[str] = None
    k: Optional[int] = None
    limit: Optional[int] = None


class ToolResponse(BaseModel):
    tool: str
    raw: Dict[str, Any]
    text: str
    tokens_est: int


def _wrap(tool_name: str, data: Dict[str, Any]) -> ToolResponse:
    text = format_response(tool_name, data)
    _TOOL_CALLS.inc(labels={"tool": tool_name})
    return ToolResponse(tool=tool_name, raw=data, text=text, tokens_est=count_tokens(text))


# ── App + lifespan ───────────────────────────────────────────────────────────
_store: Optional[GraphStore] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _store
    setup_logging(settings.DEBUG, fmt=settings.LOG_FORMAT)
    _store = await open_store()
    logger.info("CKG MCP %s booted on %s", __version__, settings.STORE_BACKEND)
    yield
    if _store is not None:
        await _store.close()


app = FastAPI(
    title="CKG MCP Server",
    description=(
        "Code Knowledge Graph — token-efficient codebase tools for AI agents. "
        "17 tools, 6 languages, SQLite or MySQL backend."
    ),
    version=__version__,
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def get_store() -> GraphStore:
    if _store is None:  # pragma: no cover
        raise HTTPException(503, "Store not initialized")
    return _store


# ── Tool endpoints ───────────────────────────────────────────────────────────
def _require(req: ToolRequest, *fields: str) -> None:
    missing = [f for f in fields if getattr(req, f) is None]
    if missing:
        raise HTTPException(400, f"missing required field(s): {', '.join(missing)}")


@app.post("/tools/get_function", response_model=ToolResponse)
async def t_get_function(req: ToolRequest, store: GraphStore = Depends(get_store)):
    _require(req, "name")
    return _wrap("get_function", await tools.get_function(store, req.name))


@app.post("/tools/get_definition", response_model=ToolResponse)
async def t_get_definition(req: ToolRequest, store: GraphStore = Depends(get_store)):
    _require(req, "name")
    return _wrap("get_definition", await tools.get_definition(store, req.name))


@app.post("/tools/search_symbol", response_model=ToolResponse)
async def t_search_symbol(req: ToolRequest, store: GraphStore = Depends(get_store)):
    _require(req, "query")
    return _wrap("search_symbol", await tools.search_symbol(store, req.query, req.type))


@app.post("/tools/get_callers", response_model=ToolResponse)
async def t_get_callers(req: ToolRequest, store: GraphStore = Depends(get_store)):
    _require(req, "name")
    return _wrap("get_callers", await tools.get_callers(store, req.name))


@app.post("/tools/get_callees", response_model=ToolResponse)
async def t_get_callees(req: ToolRequest, store: GraphStore = Depends(get_store)):
    _require(req, "name")
    return _wrap("get_callees", await tools.get_callees(store, req.name))


@app.post("/tools/call_graph", response_model=ToolResponse)
async def t_call_graph(req: ToolRequest, store: GraphStore = Depends(get_store)):
    _require(req, "name")
    return _wrap(
        "call_graph",
        await tools.call_graph(store, req.name, depth=req.depth or 2, direction=req.direction or "both"),
    )


@app.post("/tools/find_usages", response_model=ToolResponse)
async def t_find_usages(req: ToolRequest, store: GraphStore = Depends(get_store)):
    _require(req, "name")
    return _wrap("find_usages", await tools.find_usages(store, req.name))


@app.post("/tools/impact_analysis", response_model=ToolResponse)
async def t_impact_analysis(req: ToolRequest, store: GraphStore = Depends(get_store)):
    _require(req, "name")
    return _wrap(
        "impact_analysis",
        await tools.impact_analysis(store, req.name, max_depth=req.max_depth or 3),
    )


@app.post("/tools/get_subgraph", response_model=ToolResponse)
async def t_get_subgraph(req: ToolRequest, store: GraphStore = Depends(get_store)):
    _require(req, "name")
    return _wrap(
        "get_subgraph",
        await tools.get_subgraph(
            store, req.name,
            depth=req.depth or 2,
            edge_types=req.edge_types,
            direction=req.direction or "both",
        ),
    )


@app.post("/tools/find_path", response_model=ToolResponse)
async def t_find_path(req: ToolRequest, store: GraphStore = Depends(get_store)):
    _require(req, "source", "target")
    return _wrap(
        "find_path",
        await tools.find_path(store, req.source, req.target, max_hops=req.max_hops or 6),
    )


@app.post("/tools/rank_symbols", response_model=ToolResponse)
async def t_rank_symbols(req: ToolRequest, store: GraphStore = Depends(get_store)):
    return _wrap("rank_symbols", await tools.rank_symbols(store, k=req.k or 20))


@app.post("/tools/get_file_map", response_model=ToolResponse)
async def t_get_file_map(req: ToolRequest, store: GraphStore = Depends(get_store)):
    _require(req, "file_path")
    return _wrap("get_file_map", await tools.get_file_map(store, req.file_path))


@app.post("/tools/get_context", response_model=ToolResponse)
async def t_get_context(req: ToolRequest, store: GraphStore = Depends(get_store)):
    _require(req, "file_path")
    return _wrap("get_context", await tools.get_context(store, req.file_path))


@app.post("/tools/get_related", response_model=ToolResponse)
async def t_get_related(req: ToolRequest, store: GraphStore = Depends(get_store)):
    _require(req, "file_path")
    return _wrap("get_related", await tools.get_related(store, req.file_path))


@app.post("/tools/get_hierarchy", response_model=ToolResponse)
async def t_get_hierarchy(req: ToolRequest, store: GraphStore = Depends(get_store)):
    _require(req, "class_name")
    return _wrap("get_hierarchy", await tools.get_hierarchy(store, req.class_name))


@app.post("/tools/get_stats", response_model=ToolResponse)
async def t_get_stats(store: GraphStore = Depends(get_store)):
    return _wrap("get_stats", await tools.get_stats(store))


@app.post("/tools/list_languages", response_model=ToolResponse)
async def t_list_languages(store: GraphStore = Depends(get_store)):
    return _wrap("list_languages", await tools.list_languages(store))


# ── Health / discovery / metrics ─────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "ok": True,
        "version": __version__,
        "backend": settings.STORE_BACKEND,
        "tools_count": 17,
    }


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    if not settings.METRICS_ENABLED:
        raise HTTPException(404, "metrics disabled")
    return metrics_registry.render()


@app.get("/config")
async def config(agent: str = "auto"):
    """Tool definitions for any agent integration."""
    base = f"http://{settings.HOST}:{settings.MCP_PORT}"
    catalog = [
        ("get_function", "Look up function/class by name", ["name"]),
        ("get_definition", "Definition + 1-hop call graph", ["name"]),
        ("search_symbol", "Fuzzy symbol search", ["query"]),
        ("get_callers", "Who calls this function", ["name"]),
        ("get_callees", "What this function calls", ["name"]),
        ("call_graph", "N-hop caller/callee subtree", ["name"]),
        ("find_usages", "Every reference to a symbol (NEW)", ["name"]),
        ("impact_analysis", "Transitive blast radius of a change (NEW)", ["name"]),
        ("get_subgraph", "N-hop neighbourhood for arbitrary edge types (NEW)", ["name"]),
        ("find_path", "Shortest call path between two symbols (NEW)", ["source", "target"]),
        ("rank_symbols", "PageRank top-k — most important symbols (NEW)", []),
        ("get_file_map", "Symbols in a file with caller/callee counts", ["file_path"]),
        ("get_context", "Full file context — symbols + imports + refs", ["file_path"]),
        ("get_related", "Files imported by / importing this file", ["file_path"]),
        ("get_hierarchy", "Class inheritance tree", ["class_name"]),
        ("get_stats", "Repo overview", []),
        ("list_languages", "Languages parsed + grammars available (NEW)", []),
    ]
    return {
        "agent": agent,
        "base_url": base,
        "tool_count": len(catalog),
        "tools": [
            {
                "name": n,
                "description": d,
                "endpoint": f"{base}/tools/{n}",
                "required": req,
            }
            for n, d, req in catalog
        ],
    }
