from src.core.store.db import get_connection

def add_file_dependency(importer: str, importee: str):
    """Tracks a 1-to-1 import dependency for dirty set propagation."""
    conn = get_connection()
    with conn:
        conn.execute("""
            INSERT INTO file_deps (importer, importee)
            VALUES (?, ?)
            ON CONFLICT(importer, importee) DO NOTHING
        """, (importer, importee))

def delete_file_dependencies(importer: str):
    """
    When a file is modified, its imports might have been deleted, 
    so wiping the existing dependencies for this specific file prior to re-parsing is necessary.
    """
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM file_deps WHERE importer = ?", (importer,))
