from functools import lru_cache
from pathlib import Path

from pydantic import Field, PostgresDsn, field_validator
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
    anthropic_api_key: str | None = None
    anthropic_xhigh_model: str = "claude-sonnet-4-20250514"

    # LangFuse
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # VFS
    workspace_root: Path = Field(default=_DEFAULT_WORKSPACE)

    # Tavily MCP (pre-built official server — no custom MCP)
    tavily_api_key: str | None = None
    tavily_mcp_url: str = "https://mcp.tavily.com/mcp"

    # MCP research servers (JSON string → parsed in client setup)
    mcp_servers_json: str = "{}"

    # App
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    streamlit_port: int = 8501
    log_level: str = "INFO"

    @field_validator("workspace_root", mode="before")
    @classmethod
    def resolve_workspace_root(cls, value: str | Path) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = _PROJECT_ROOT / path
        return path.resolve()

    @property
    def is_langfuse_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

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
