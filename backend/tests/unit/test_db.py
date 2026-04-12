import pytest
import os
from src.core.store.db import get_connection, init_db
from src.core.store.hash_registry import update_file_hash, get_stored_hashes, delete_file_hash

def test_db_init_and_hash_registry():
    """Validates the SQLite database initialization and the hashing data access layer"""
    # 1. Test database bootstrap handles schemas cleanly
    conn = init_db()
    assert conn is not None
    
    # 2. Test Hash Registry logic
    test_path = "/fake/repo/test.py"
    test_hash = "abc123hash_mock"
    size = 1024
    lang = "python"
    
    # Upsert test
    update_file_hash(test_path, test_hash, size, lang)
    hashes = get_stored_hashes()
    
    assert test_path in hashes
    assert hashes[test_path] == test_hash
    
    # Deletion test
    delete_file_hash(test_path)
    hashes = get_stored_hashes()
    assert test_path not in hashes
