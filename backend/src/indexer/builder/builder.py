import time
from src.core.store.db import get_connection
from src.core.store.hash_registry import update_file_hash, delete_file_hash
from src.indexer.dirty_set.dirty_set import build_dirty_set
from src.indexer.propagator.propagator import propagate_dirty_set

def run_pipeline(repo_path: str):
    """Orchestrates Phase 1: Scanning, hashing, and storing."""
    print("Starting index rebuild pipeline...")
    start_time = time.time()
    
    conn = get_connection()
    
    # 1. Scanner & Dirty Set
    print("Building dirty set...")
    dirty_files, deleted_files = build_dirty_set(repo_path)
    
    # 2. Propagate dirty set to reverse dependencies (Step 4)
    print("Propagating dirty set to importers...")
    dirty_files = propagate_dirty_set(dirty_files)
    
    # 3. Handle deleted files
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

from src.core.store.hash_registry import get_stored_hashes

def run_single_file_pipeline(filepath: str):
    """
    Orchestrates Phase 1: Specifically for a single file triggered by watchdog.
    Runs exactly the same logic but perfectly scoped.
    """
    import os
    from src.indexer.scanner.scanner import compute_sha256, SUPPORTED_EXTENSIONS
    
    conn = get_connection()
    stored_hashes = get_stored_hashes()
    
    # Handle deletion events fired by watchdog
    if not os.path.exists(filepath):
        if filepath in stored_hashes:
            print(f"File Deleted (Watcher): {filepath}")
            delete_file_hash(filepath)
            # TODO: Delete nodes & edges associated with this file_path here
        return
        
    ext = os.path.splitext(filepath)[1]
    lang = SUPPORTED_EXTENSIONS.get(ext, "unknown")
    
    computed_hash = compute_sha256(filepath)
    size = os.path.getsize(filepath)
    
    # If the file hasn't actually structurally changed (just a format triggering save)
    # Then sha256 matches, and we skip it.
    if filepath not in stored_hashes or stored_hashes[filepath] != computed_hash:
        dirty_files = [{
            "path": filepath,
            "sha256": computed_hash,
            "language": lang,
            "size": size
        }]
        
        # Propagate properly (Step 4 applies locally too!)
        dirty_files = propagate_dirty_set(dirty_files)
        
        for file_info in dirty_files:
            target_path = file_info["path"]
            print(f"Processing (Tree-sitter parse mock): {target_path}")
            
            # TODO: Step 5 Parse & Extract
            
            # Step 6: Update Hash Registry
            update_file_hash(
                path=target_path, 
                sha256=file_info["sha256"], 
                file_size=file_info["size"], 
                language=file_info["language"]
            )
