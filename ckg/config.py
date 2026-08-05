"""Centralized settings for every CKG entry point.

Single Settings object. CLI, MCP server, and indexer all import from here
so there's no drift between sub-services. Reads from a `.env` file or the
process environment.
"""
from __future__ import annotations

from typing import Dict, List, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration for CKG — loaded from env / .env at startup."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        env_prefix="CKG_",
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────────────────
    APP_NAME: str = "CKG - Code Knowledge Graph"
    APP_VERSION: str = "3.0.0"
    DEBUG: bool = False
    LOG_FORMAT: Literal["text", "json"] = "text"

    # ── Storage backend ──────────────────────────────────────────────────────
    # "sqlite" — zero-setup, file-based, perfect for solo / dev (NEW default)
    # "mysql"  — original docker-compose stack
    STORE_BACKEND: Literal["sqlite", "mysql"] = "sqlite"
    SQLITE_PATH: str = ".ckg/graph.db"

    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "ckg_user"
    MYSQL_PASSWORD: str = "ckg_password"
    MYSQL_DATABASE: str = "ckg"

    # ── Indexer ──────────────────────────────────────────────────────────────
    REPO_PATH: str = ""
    WATCHER_DEBOUNCE_MS: int = 300
    MAX_FILE_SIZE_KB: int = 512
    BATCH_SIZE: int = 50
    YIELD_EVERY_FILES: int = 3  # Cooperative yield to event loop

    # ── HTTP ─────────────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    MCP_PORT: int = 8001

    # ── MCP token budget ─────────────────────────────────────────────────────
    MAX_TOKENS_PER_RESPONSE: int = 400
    MAX_RESULTS: int = 20

    # ── Observability ────────────────────────────────────────────────────────
    METRICS_ENABLED: bool = True
    METRICS_PORT: int = 9090

    # ── File patterns ────────────────────────────────────────────────────────
    IGNORE_DIRS: List[str] = Field(
        default_factory=lambda: [
            "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
            "dist", "build", ".next", ".nuxt", "coverage", ".pytest_cache",
            ".mypy_cache", ".ruff_cache", "target", "out", ".idea", ".vscode",
            ".gradle", ".cargo", "vendor", "Pods", ".tox",
        ]
    )
    IGNORE_FILE_PATTERNS: List[str] = Field(
        default_factory=lambda: [
            "*.min.js", "*.min.css", "*.map", "*.lock",
            "package-lock.json", "yarn.lock", "poetry.lock",
            "Cargo.lock", "go.sum",
        ]
    )

    SUPPORTED_EXTENSIONS: Dict[str, str] = Field(
        default_factory=lambda: {
            # Python
            ".py": "python",
            ".pyi": "python",
            # TypeScript / JavaScript
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "javascript",
            ".jsx": "javascript",
            ".mjs": "javascript",
            ".cjs": "javascript",
            # Go
            ".go": "go",
            # Rust
            ".rs": "rust",
            # Java
            ".java": "java",
            # C / C++
            ".c": "c",
            ".h": "c",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".cxx": "cpp",
            ".hpp": "cpp",
            # Ruby
            ".rb": "ruby",
        }
    )

    # ── Derived ──────────────────────────────────────────────────────────────
    @property
    def DATABASE_URL(self) -> str:
        if self.STORE_BACKEND == "sqlite":
            return f"sqlite+aiosqlite:///{self.SQLITE_PATH}"
        return (
            f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
            "?charset=utf8mb4"
        )


# Module-level singleton — every component imports the same instance.
settings = Settings()
