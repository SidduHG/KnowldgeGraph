import sqlite3
import os

DB_PATH = os.path.join(os.getcwd(), ".ckg", "graph.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "graph", "schema", "schema.sql")

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Enable foreign keys for SQLite
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    """Initializes the database schema if it doesn't already exist."""
    print(f"Initializing database at {DB_PATH}")
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    conn = get_connection()
    with open(SCHEMA_PATH, "r") as f:
        schema_sql = f.read()
    
    with conn:
        conn.executescript(schema_sql)
    
    print("Database schema successfully migrated!")
    return conn
