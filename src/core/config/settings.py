from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, PostgresDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_WORKSPACE = _PROJECT_ROOT / "src" / "workspace"


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # PostgreSQL / checkpointer
    postgres_user: str = "pt_ai"
    postgres_password: str = "pt_ai_dev"
    postgres_db: str = "pt_ai_core"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    database_url: PostgresDsn | None = None

    # LLM — Reasoning Sandwich tiers
    openai_api_key: str | None = None
    openai_standard_model: str = "gpt-4o-mini"
    openai_xhigh_model: str = "gpt-4o"
    anthropic_api_key: str | None = None
    anthropic_xhigh_model: str = "claude-sonnet-4-20250514"

    # LangFuse — prefer LANGFUSE_BASE_URL; LANGFUSE_HOST is a legacy alias
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_base_url: str = "http://localhost:3000"
    langfuse_tracing_enabled: bool = True

    # VFS
    workspace_root: Path = Field(default=_DEFAULT_WORKSPACE)

    # Tavily MCP (pre-built official server — no custom MCP)
    tavily_api_key: str | None = None
    tavily_mcp_url: str = "https://mcp.tavily.com/mcp"
    mock_research: bool = False

    # Research Agent
    research_max_search_iterations: int = 3
    research_extract_top_k: int = 8
    research_trusted_domains: str = ""

    # MCP research servers (JSON string → parsed in client setup)
    mcp_servers_json: str = "{}"

    # App
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    streamlit_port: int = 8501
    api_base_url: str = "http://localhost:8000"
    log_level: str = "INFO"

    @model_validator(mode="before")
    @classmethod
    def resolve_langfuse_base_url(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if data.get("langfuse_base_url"):
            return data
        base_url = data.get("LANGFUSE_BASE_URL")
        host = data.get("LANGFUSE_HOST") or data.get("langfuse_host")
        resolved = base_url or host
        if resolved:
            data["langfuse_base_url"] = resolved
        return data

    @field_validator("mock_research", mode="before")
    @classmethod
    def parse_mock_research(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return False

    @field_validator("langfuse_tracing_enabled", mode="before")
    @classmethod
    def parse_langfuse_tracing_enabled(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() not in {"0", "false", "no", "off"}
        return True

    @field_validator("workspace_root", mode="before")
    @classmethod
    def resolve_workspace_root(cls, value: str | Path) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = _PROJECT_ROOT / path
        return path.resolve()

    @property
    def is_langfuse_enabled(self) -> bool:
        return bool(
            self.langfuse_tracing_enabled and self.langfuse_public_key and self.langfuse_secret_key
        )

    @property
    def langfuse_host(self) -> str:
        """Deprecated alias kept for backward compatibility."""
        return self.langfuse_base_url

    @property
    def checkpointer_dsn(self) -> str:
        if self.database_url:
            return str(self.database_url)
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
