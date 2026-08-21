"""Application configuration management.

Environment detection, ``.env`` file resolution and configuration parsing via
pydantic-settings. This module is the only place in the application allowed to read
the process environment.
"""

import os
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Environment(StrEnum):
    """Application environment types."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


def get_environment() -> Environment:
    """Get the current environment from ``APP_ENV``.

    Returns:
        Environment: The current environment (development, staging or production).
    """
    value = os.getenv("APP_ENV", "development").lower()
    if value in ("production", "prod"):
        return Environment.PRODUCTION
    if value in ("staging", "stage"):
        return Environment.STAGING
    return Environment.DEVELOPMENT


def find_project_root() -> Path:
    """Locate the repository root by walking up to the directory holding ``pyproject.toml``.

    Counting ``dirname`` calls from ``__file__`` is what this replaces: that breaks silently
    the moment the module moves between directories, and the failure mode is not an error
    but an env file that is quietly never loaded.

    Returns:
        Path: The project root, or this module's own directory if no marker is found.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return here.parent


def load_env_file() -> str | None:
    """Resolve the environment-specific ``.env`` file path.

    Returns the first existing file in priority order — ``.env.<env>.local`` beats
    ``.env.<env>``, which beats ``.env.local``, which beats ``.env``. Only that one file is
    loaded; the rest are ignored rather than merged.

    Returns:
        str | None: Absolute path to the env file, or None if none was found.
    """
    root = find_project_root()
    env = get_environment().value
    for name in (f".env.{env}.local", f".env.{env}", ".env.local", ".env"):
        candidate = root / name
        if candidate.is_file():
            return str(candidate)
    return None


ENV_FILE = load_env_file()


def _parse_csv_list(value: Any) -> Any:
    """Normalize a CSV string or list value for pydantic field validators."""
    if isinstance(value, list):
        return value
    if not isinstance(value, str):
        return value
    return [item.strip().strip("\"'") for item in value.split(",") if item.strip()]


_DEFAULT_RATE_LIMIT_ENDPOINTS: dict[str, list[str]] = {
    "chat": ["30 per minute"],
    "chat_stream": ["20 per minute"],
    "messages": ["50 per minute"],
    "resume": ["30 per minute"],
}


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    ENVIRONMENT: Environment = Field(default_factory=get_environment)

    # --- Application -----------------------------------------------------------------
    PROJECT_NAME: str = "Fitness Coaching Graph"
    VERSION: str = "0.1.0"
    DESCRIPTION: str = (
        "Fitness coaching and knowledge QA assistant built on a LangGraph state graph."
    )
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False
    ALLOWED_ORIGINS: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["*"])

    # --- Observability ---------------------------------------------------------------
    LANGFUSE_TRACING_ENABLED: bool = True
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_HOST: str = Field(
        default="https://cloud.langfuse.com",
        validation_alias=AliasChoices("LANGFUSE_HOST", "LANGFUSE_BASE_URL"),
    )

    # --- LLM -------------------------------------------------------------------------
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    DEFAULT_LLM_MODEL: str = "gpt-5-mini"
    DEFAULT_LLM_TEMPERATURE: float = 0.2
    MAX_TOKENS: int = 2000
    MAX_LLM_CALL_RETRIES: int = 3
    LLM_TOTAL_TIMEOUT: int = 60

    # --- Graph retry limits (spec §9: every limit is a counter in GraphState) ---------
    COACH_MAX_RETRIES: int = 3
    HITL_MAX_RETRIES: int = 3
    QA_MAX_RETRIES: int = 3

    # --- Knowledge base / RAG (spec §8) ----------------------------------------------
    KNOWLEDGE_EMBEDDER_MODEL: str = "text-embedding-3-small"
    KNOWLEDGE_EMBEDDING_DIM: int = 1536
    KNOWLEDGE_TOP_K: int = 4
    KNOWLEDGE_MIN_SCORE: float = 0.3
    RAGAS_FAITHFULNESS_THRESHOLD: float = 0.9

    # --- Postgres --------------------------------------------------------------------
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "coaching_db"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_POOL_SIZE: int = 20
    POSTGRES_MAX_OVERFLOW: int = 10
    DATABASE_URL: str = ""

    LONG_TERM_STORE_INDEX_DIMS: int = 1536

    # --- Rate limiting ---------------------------------------------------------------
    RATE_LIMIT_DEFAULT: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["200 per day", "50 per hour"]
    )
    RATE_LIMIT_ENDPOINTS: dict[str, list[str]] = Field(
        default_factory=lambda: _DEFAULT_RATE_LIMIT_ENDPOINTS.copy()
    )

    # --- Logging ---------------------------------------------------------------------
    LOG_DIR: Path = Path("logs")
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    @field_validator("ALLOWED_ORIGINS", "RATE_LIMIT_DEFAULT", mode="before")
    @classmethod
    def parse_list_fields(cls, value: Any) -> Any:
        """Parse comma-separated env strings into ``list[str]``."""
        return _parse_csv_list(value)

    @property
    def sqlalchemy_database_uri(self) -> str:
        """SQLAlchemy URL for the application tables.

        Returns ``DATABASE_URL`` when set, otherwise assembles a psycopg3 Postgres URL from
        the ``POSTGRES_*`` parts. A bare ``postgresql://`` override is rewritten to name
        psycopg3 explicitly, since SQLAlchemy would otherwise default to psycopg2, which is
        not a dependency of this project.

        Returns:
            str: The SQLAlchemy connection URL.
        """
        if self.DATABASE_URL:
            if self.DATABASE_URL.startswith("postgresql://"):
                return self.DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
            return self.DATABASE_URL
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def psycopg_database_uri(self) -> str:
        """Raw psycopg DSN for the LangGraph checkpointer and store pools.

        Same database as ``sqlalchemy_database_uri``, different driver surface: the
        checkpointer opens its own ``psycopg_pool.AsyncConnectionPool`` and cannot parse
        SQLAlchemy's ``postgresql+psycopg://`` prefix.

        Returns:
            str: The psycopg connection DSN.
        """
        return self.sqlalchemy_database_uri.replace("postgresql+psycopg://", "postgresql://", 1)

    @model_validator(mode="after")
    def apply_environment_settings(self) -> "Settings":
        """Apply environment-specific presets on top of the loaded values."""
        presets: dict[Environment, dict[str, Any]] = {
            Environment.DEVELOPMENT: {"DEBUG": True, "LOG_FORMAT": "console"},
            Environment.STAGING: {"DEBUG": False, "LOG_LEVEL": "INFO"},
            Environment.PRODUCTION: {"DEBUG": False, "LOG_LEVEL": "WARNING"},
        }
        for key, value in presets.get(self.ENVIRONMENT, {}).items():
            if key.upper() not in os.environ:
                object.__setattr__(self, key, value)
        return self


settings = Settings()
