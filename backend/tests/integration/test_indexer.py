import os
import pytest
import asyncio
from pathlib import Path

from app.config import settings
from app.database.connection import init_db, close_db
from app.core.indexer import IndexerService

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()
    yield
    await close_db()

@pytest.mark.asyncio
async def test_full_index_flow(tmp_path):
    repo = tmp_path / "mock_repo"
    repo.mkdir()
    
    # Create mock Python file
    (repo / "main.py").write_text("def start_app(): pass", encoding="utf-8")
    
    # Create mock JS file
    (repo / "utils.js").write_text("function add(a, b) { return a + b; }", encoding="utf-8")
    
    # Run integration indexer
    idx = IndexerService.get()
    prog = await idx.run_full(str(repo))
    
    assert prog.ok or prog.status == "completed"
    assert prog.files_done >= 2
    assert prog.nodes_created >= 2
