import os
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.core.store.db import init_db
from src.indexer.watcher.watcher import start_watcher

# Lifecycle manager allows code to run safely upon startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the complex SQLite schema + FTS5
    await init_db()
    
    # Spin off the debounced Watchdog event loop into a non-blocking background thread
    # So it doesn't halt the FastAPI web server from accepting requests
    repo_path = os.path.dirname(os.path.dirname(os.getcwd())) # Lock onto KnowldgeGraph root
    watcher_thread = threading.Thread(target=start_watcher, args=(repo_path,), daemon=True)
    watcher_thread.start()
    
    yield

app = FastAPI(lifespan=lifespan)

# Configure CORS so the frontend can communicate with the backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Welcome to the FastAPI Backend!"}

@app.get("/api/health")
def health_check():
    return {"status": "ok"}

