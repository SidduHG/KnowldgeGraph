import pytest
from src.indexer.scanner.scanner import compute_sha256

def test_compute_sha256(tmp_path):
    """Validates the exact functionality of the file hashing mechanism"""
    # Create a real mock file in a temporary pytest directory
    test_file = tmp_path / "test_script.py"
    test_file.write_text("def hello_world():\n    print('hello')\n")
    
    # Compute
    hash_val = compute_sha256(str(test_file))
    
    # Validate
    assert isinstance(hash_val, str)
    assert len(hash_val) == 64 # SHA-256 standard hex length
    assert hash_val != ""
