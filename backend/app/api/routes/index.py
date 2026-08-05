from __future__ import annotations
from typing import Optional
import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException
from app.api.schemas import IndexRequest, IndexResponse, WatchRequest, WatchResponse
from app.core.indexer import IndexerService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/index", tags=["index"])

# ── State for watcher ───────────────────────────────────────────────────────
_watch_state: dict = {"watching": False, "repo_path": None}


def _progress_to_response(prog) -> IndexResponse:
    return IndexResponse(
        status=str(prog.status.value) if hasattr(prog.status, "value") else str(prog.status),
        run_type=prog.run_type,
        repo_path=prog.repo_path,
        files_total=prog.files_total,
        files_done=prog.files_done,
        files_skipped=prog.files_skipped,
        nodes_created=prog.nodes_created,
        edges_created=prog.edges_created,
        errors=prog.errors,
        elapsed_ms=prog.elapsed_ms,
        pct=prog.pct,
        error_message=prog.error_message,
    )


@router.get("/status", response_model=IndexResponse)
async def get_index_status():
    """Return the current indexing progress / last run status."""
    prog = IndexerService.get().progress
    return _progress_to_response(prog)


@router.post("", response_model=IndexResponse)
async def trigger_index(req: IndexRequest, background_tasks: BackgroundTasks):
    svc = IndexerService.get()

    # If stuck from a previous crash, reset to IDLE
    if svc.is_running:
        # Check if it's truly stuck (running for >5 minutes with no progress)
        import time
        elapsed = time.time() - svc.progress.started_at if svc.progress.started_at else 0
        if elapsed > 300:
            logger.warning("Resetting stuck indexer (was running for %.0fs)", elapsed)
            svc.reset()
        else:
            raise HTTPException(status_code=400, detail="Indexing already in progress")

    # Run indexing in a background coroutine
    async def _run():
        try:
            await svc.run_full(req.repo_path)
        except Exception as e:
            logger.error("Background index failed: %s", e)

    background_tasks.add_task(_run)

    # Give the background task a moment to start
    await asyncio.sleep(0.1)

    # Return current progress snapshot
    return _progress_to_response(svc.progress)


# ── Reset endpoint (force-clear stuck state) ──────────────────────────────
@router.post("/reset", response_model=IndexResponse)
async def reset_index():
    """Force-reset the indexer from a stuck RUNNING state."""
    svc = IndexerService.get()
    svc.reset()
    return _progress_to_response(svc.progress)


@router.get("/watch", response_model=WatchResponse)
async def get_watch_status():
    """Return whether the file watcher is active."""
    return WatchResponse(
        watching=_watch_state["watching"],
        repo_path=_watch_state["repo_path"],
    )


@router.post("/watch", response_model=WatchResponse)
async def control_watch(req: WatchRequest):
    """Start or stop the file watcher."""
    global _watch_state
    if req.action == "start":
        _watch_state = {"watching": True, "repo_path": req.repo_path}
    elif req.action == "stop":
        _watch_state = {"watching": False, "repo_path": None}
    else:
        raise HTTPException(status_code=400, detail="action must be 'start' or 'stop'")
    return WatchResponse(
        watching=_watch_state["watching"],
        repo_path=_watch_state["repo_path"],
    )
