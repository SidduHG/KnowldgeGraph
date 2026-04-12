import os
from src.indexer.scanner.scanner import walk_repo, compute_sha256
from src.core.store.hash_registry import get_stored_hashes

def build_dirty_set(repo_path: str):
    """
    Compares the current repository state against the database stored hashes.
    Returns:
    - dirty_files: List of (filepath, sha256, language, file_size) that changed/added.
    - deleted_files: List of filepaths that no longer exist.
    """
    stored_hashes = get_stored_hashes()
    current_files = {}
    
    dirty_files = []
    
    for filepath, lang in walk_repo(repo_path):
        current_files[filepath] = True
        
        computed_hash = compute_sha256(filepath)
        size = os.path.getsize(filepath)
        
        # If it doesn't exist in DB, or hash is different -> it's dirty
        if filepath not in stored_hashes or stored_hashes[filepath] != computed_hash:
            dirty_files.append({
                "path": filepath,
                "sha256": computed_hash,
                "language": lang,
                "size": size
            })
            
    # Find files that were deleted
    deleted_files = [path for path in stored_hashes.keys() if path not in current_files]
    
    return dirty_files, deleted_files
