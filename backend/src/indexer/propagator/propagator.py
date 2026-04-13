import os
from src.core.store.db import get_connection
from src.indexer.scanner.scanner import compute_sha256, SUPPORTED_EXTENSIONS

def propagate_dirty_set(dirty_files: list) -> list:
    """
    Step 4: Dirty set propagation.
    For every file in the dirty set, look up file_deps WHERE importee = that_file. 
    Every importer found gets added to the dirty set too (one hop only).
    """
    if not dirty_files:
        return dirty_files

    conn = get_connection()
    cursor = conn.cursor()
    
    # Extract unique dirty paths
    dirty_paths = [f["path"] for f in dirty_files]
    dirty_path_set = set(dirty_paths)
    
    # To handle large lists safely in SQLite, we chunk if > 900
    chunk_size = 900
    importers = []
    
    for i in range(0, len(dirty_paths), chunk_size):
        chunk = dirty_paths[i:i + chunk_size]
        placeholders = ",".join(["?"] * len(chunk))
        query = f"SELECT DISTINCT importer FROM file_deps WHERE importee IN ({placeholders})"
        cursor.execute(query, chunk)
        importers.extend([row["importer"] for row in cursor.fetchall()])

    # We append to the original list so we don't mutate input by reference if not wanted, 
    # but returning a fresh combined list is safer.
    propagated_dirty_files = list(dirty_files)
    
    for importer_path in importers:
        # Check if it was already marked dirty or got deleted
        if importer_path not in dirty_path_set and os.path.exists(importer_path):
            dirty_path_set.add(importer_path)
            
            # Recompute core properties to pass down to parser and cache
            size = os.path.getsize(importer_path)
            computed_hash = compute_sha256(importer_path)
            ext = os.path.splitext(importer_path)[1]
            lang = SUPPORTED_EXTENSIONS.get(ext, "unknown")
            
            propagated_dirty_files.append({
                "path": importer_path,
                "sha256": computed_hash,
                "language": lang,
                "size": size,
                "propagated": True # Explicit flag to mark that this was a reverse-dep pull
            })
            
    return propagated_dirty_files
