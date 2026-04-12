from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List, Dict
import json

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # ── App ──────────────────────────────────────────────────────────────────
    APP_NAME: str = "CKG - Code Knowledge Graph"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # ── MySQL ─────────────────────────────────────────────────────────────────
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "ckg_user"
    MYSQL_PASSWORD: str = "ckg_password"
    MYSQL_DATABASE: str = "ckg"

    # ── Indexer ───────────────────────────────────────────────────────────────
    REPO_PATH: str = ""
    WATCHER_DEBOUNCE_MS: int = 300
    MAX_FILE_SIZE_KB: int = 512          # skip files larger than this
    BATCH_SIZE: int = 50                 # files per transaction batch

    # ── Patterns ──────────────────────────────────────────────────────────────
    IGNORE_DIRS: List[str] = [
        "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
        "dist", "build", ".next", ".nuxt", "coverage", ".pytest_cache",
        ".mypy_cache", ".ruff_cache", "target", "out", ".idea", ".vscode",
    ]
    IGNORE_FILE_PATTERNS: List[str] = [
        "*.min.js", "*.min.css", "*.map", "*.lock",
        "package-lock.json", "yarn.lock", "poetry.lock",
    ]
    SUPPORTED_EXTENSIONS: Dict[str, str] = {
        ".py":   "python",
        ".ts":   "typescript",
        ".tsx":  "typescript",
        ".js":   "javascript",
        ".jsx":  "javascript",
    }

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
            "?charset=utf8mb4"
        )

    @property
    def DATABASE_URL_SYNC(self) -> str:
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
            "?charset=utf8mb4"
        )

settings = Settings()
