from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.api.schemas import IndexRequest, IndexResponse, WatchRequest, WatchResponse
from app.core.indexer import IndexerService

router = APIRouter(prefix="/index", tags=["index"])

@router.post("", response_model=IndexResponse)
async def trigger_index(req: IndexRequest):
    if IndexerService.get().is_running:
        raise HTTPException(status_code=400, detail="Indexing already in progress")
    
    prog = await IndexerService.get().run_full(req.repo_path)
    return IndexResponse(
        status=prog.status,
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
        error_message=prog.error_message
    )
