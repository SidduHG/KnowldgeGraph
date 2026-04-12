import time
from src.core.store.db import get_connection
from src.core.store.hash_registry import update_file_hash, delete_file_hash
from src.indexer.dirty_set.dirty_set import build_dirty_set

def run_pipeline(repo_path: str):
    """Orchestrates Phase 1: Scanning, hashing, and storing."""
    print("Starting index rebuild pipeline...")
    start_time = time.time()
    
    conn = get_connection()
    
    # 1. Scanner & Dirty Set
    print("Building dirty set...")
    dirty_files, deleted_files = build_dirty_set(repo_path)
    
    # 2. Handle deleted files
    for deleted_file in deleted_files:
        print(f"File Deleted: {deleted_file}")
        delete_file_hash(deleted_file)
        # TODO: Delete nodes & edges associated with this file_path here
    
    # 3. Handle dirty/new files
    print(f"Found {len(dirty_files)} dirty files to process.")
    for file_info in dirty_files:
        filepath = file_info["path"]
        print(f"Processing (Tree-sitter parse mock): {filepath}")
        
        # TODO: Step 5 Parse & Extract goes here. (tree-sitter AST extraction)
        
        # Step 6: Update Hash Registry 
        update_file_hash(
            path=filepath, 
            sha256=file_info["sha256"], 
            file_size=file_info["size"], 
            language=file_info["language"]
        )

    duration = time.time() - start_time
    print(f"Pipeline completed in {duration:.2f}s.")
