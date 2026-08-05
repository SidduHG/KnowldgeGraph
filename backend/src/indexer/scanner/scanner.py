import os
import hashlib

IGNORED_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", ".ckg", "build", "dist", "target", "out", "bin", "obj", ".env"}
SUPPORTED_EXTENSIONS = {
    ".py": "python",
    ".ts": "typescript",
    ".js": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".php": "php",
    ".rb": "ruby",
    ".swift": "swift",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".fish": "bash",
    ".ps1": "powershell",
    ".psm1": "powershell",
    ".fs": "fsharp",    
    ".fsi": "fsharp",
    ".fsx": "fsharp",
    ".fsx": "fsharp",
    ".jsx": "javascript",
    ".tsx": "typescript",
}

def walk_repo(root_path: str):
    """Walks the repository and yields valid file paths."""
    for root, dirs, files in os.walk(root_path):
        # Prevent walking into ignored directories
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
        
        for file in files:
            ext = os.path.splitext(file)[1]
            if ext in SUPPORTED_EXTENSIONS:
                yield os.path.join(root, file), SUPPORTED_EXTENSIONS[ext]

def compute_sha256(filepath: str) -> str:
    """Computes the SHA256 configuration for a file."""
    hasher = hashlib.sha256()
    try:
        with open(filepath, 'rb') as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        return ""
