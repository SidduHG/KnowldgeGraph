from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ── Index ──────────────────────────────────────────────────────────────────────
class IndexRequest(BaseModel):
    repo_path: str = Field(..., description="Absolute path to the repository")
    force: bool = Field(False, description="Force re-index all files")


class IndexResponse(BaseModel):
    status: str
    run_type: str
    repo_path: str
    files_total: int
    files_done: int
    files_skipped: int
    nodes_created: int
    edges_created: int
    errors: int
    elapsed_ms: int
    pct: int
    error_message: str


# ── Status ─────────────────────────────────────────────────────────────────────
class HealthResponse(BaseModel):
    ok: bool
    version: str
    db: str


class StatsResponse(BaseModel):
    total_files: int
    total_nodes: int
    total_edges: int
    node_types: Dict[str, int]
    edge_types: Dict[str, int]
    last_run: Optional[Dict[str, Any]]


# ── Watcher ────────────────────────────────────────────────────────────────────
class WatchRequest(BaseModel):
    repo_path: str
    action: str = Field(..., description="start | stop")


class WatchResponse(BaseModel):
    watching: bool
    repo_path: Optional[str]


# ── Graph ──────────────────────────────────────────────────────────────────────
class NodeOut(BaseModel):
    id: str
    type: str
    name: str
    qualified_name: Optional[str]
    file_path: str
    start_line: Optional[int]
    end_line: Optional[int]
    signature: Optional[str]
    docstring: Optional[str]
    language: Optional[str]


class EdgeOut(BaseModel):
    id: str
    source_id: str
    target_id: str
    type: str
    file_path: Optional[str]


class FileMapResponse(BaseModel):
    file_path: str
    nodes: List[NodeOut]
    edges: List[EdgeOut]
