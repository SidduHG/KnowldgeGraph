from src.core.store.db import get_connection

def get_stored_hashes():
    """Returns a dictionary of {file_path: sha256_hash} from the db."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT path, sha256 FROM file_hashes")
    results = {row["path"]: row["sha256"] for row in cursor.fetchall()}
    return results

def update_file_hash(path: str, sha256: str, file_size: int, language: str):
    """Upserts a new hash into the hash registry."""
    conn = get_connection()
    with conn:
        conn.execute("""
            INSERT INTO file_hashes (path, sha256, file_size, language, analyzed_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(path) DO UPDATE SET 
                sha256=excluded.sha256, 
                file_size=excluded.file_size,
                language=excluded.language,
                analyzed_at=CURRENT_TIMESTAMP
        """, (path, sha256, file_size, language))

def delete_file_hash(path: str):
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM file_hashes WHERE path = ?", (path,))
