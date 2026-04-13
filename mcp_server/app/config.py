from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import Literal


class MCPSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

    # ── MySQL (same DB as backend) ─────────────────────────────────────────────
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "ckg_user"
    MYSQL_PASSWORD: str = "ckg_password"
    MYSQL_DATABASE: str = "ckg"

    # ── Server mode ────────────────────────────────────────────────────────────
    # claude   → MCP stdio transport  (Claude Code / claude mcp add)
    # http     → REST JSON API        (Codex, Gemini, Cursor via HTTP tool calls)
    # both     → start HTTP server AND expose MCP stdio
    MODE: Literal["claude", "http", "both"] = "both"

    HOST: str = "0.0.0.0"
    PORT: int = 8001

    # ── Token budget ──────────────────────────────────────────────────────────
    MAX_TOKENS_PER_RESPONSE: int = 400
    MAX_RESULTS: int = 20

    # ── Agent identity (used in /config endpoint) ─────────────────────────────
    AGENT: str = "auto"   # claude | codex | gemini | cursor | auto

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
            "?charset=utf8mb4"
        )


settings = MCPSettings()
