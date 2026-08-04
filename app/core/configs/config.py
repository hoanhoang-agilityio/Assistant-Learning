"""Application configuration management.

This module handles environment-specific configuration loading, parsing, and management
for the application. It includes environment detection, .env file loading, and
configuration value parsing via pydantic BaseSettings.
"""

import os
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Environment(StrEnum):
    """Application environment types.

    Defines the possible environments the application can run in:
    development, staging, and production.
    """

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


def get_environment() -> Environment:
    """Get the current environment.

    Returns:
        Environment: The current environment (development, staging, or production)
    """
    match os.getenv("APP_ENV", "development").lower():
        case "production" | "prod":
            return Environment.PRODUCTION
        case "staging" | "stage":
            return Environment.STAGING
        case _:
            return Environment.DEVELOPMENT


def find_project_root() -> Path:
    """Locate the repository root by walking up to the directory holding pyproject.toml.

    Counting ``dirname`` calls from ``__file__`` is what this replaces: that
    breaks silently the moment the module moves between directories, and the
    failure mode is not an error but an env file that is quietly never loaded.

    Returns:
        Path: The project root, or this module's own directory if no marker is found.
    """
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return here.parent


def load_env_file() -> str | None:
    """Resolve environment-specific .env file path.

    Returns the first existing file in priority order — ``.env.<env>.local``
    beats ``.env.<env>``, which beats ``.env.local``, which beats ``.env``. Only
    that one file is loaded; the rest are ignored rather than merged.

    Returns:
        str | None: Absolute path to the env file, or None if none found.
    """
    env = get_environment()
    base_dir = find_project_root()
    env_files = [
        base_dir / f".env.{env.value}.local",
        base_dir / f".env.{env.value}",
        base_dir / ".env.local",
        base_dir / ".env",
    ]
    for env_file in env_files:
        if env_file.is_file():
            return str(env_file)
    return None


ENV_FILE = load_env_file()


def parse_list_from_env(env_key: str, default: list[str] | None = None) -> list[str]:
    """Parse a comma-separated list from an environment variable."""
    value = os.getenv(env_key)
    if not value:
        return default or []
    value = value.strip("\"'")
    if "," not in value:
        return [value]
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_dict_of_lists_from_env(
    prefix: str, default_dict: dict[str, list[str]] | None = None
) -> dict[str, list[str]]:
    """Parse dictionary of lists from environment variables with a common prefix."""
    result = default_dict or {}
    for key, value in os.environ.items():
        if key.startswith(prefix):
            endpoint = key[len(prefix) :].lower()
            if value:
                value = value.strip("\"'")
                if "," in value:
                    result[endpoint] = [item.strip() for item in value.split(",") if item.strip()]
                else:
                    result[endpoint] = [value]
    return result


def _parse_csv_list(value: Any) -> list[str]:
    """Normalize CSV string or list values for pydantic field validators."""
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip("\"'")
    if "," not in text:
        return [text] if text else []
    return [item.strip() for item in text.split(",") if item.strip()]


_DEFAULT_RATE_LIMIT_ENDPOINTS: dict[str, list[str]] = {
    "chat": ["30 per minute"],
    "chat_stream": ["20 per minute"],
    "messages": ["50 per minute"],
    "register": ["10 per hour"],
    "login": ["20 per minute"],
    "refresh": ["30 per hour"],
    "root": ["10 per minute"],
    "health": ["20 per minute"],
}


class Settings(BaseSettings):
    """Application settings using pydantic BaseSettings."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE if ENV_FILE else None,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    ENVIRONMENT: Environment = Field(default_factory=get_environment)

    PROJECT_NAME: str = "Personal AI Chatbot"
    VERSION: str = "1.0.0"
    DESCRIPTION: str = "A personalized AI chatbot for personal use."
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False

    ALLOWED_ORIGINS: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["*"])

    LANGFUSE_TRACING_ENABLED: bool = True
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

    OPENAI_API_KEY: str = ""
    DEFAULT_LLM_MODEL: str = "gpt-5-mini"
    SESSION_NAMING_ENABLED: bool = True
    DEFAULT_LLM_TEMPERATURE: float = 0.2
    MAX_TOKENS: int = 2000
    MAX_LLM_CALL_RETRIES: int = 3
    LLM_TOTAL_TIMEOUT: int = 60

    LONG_TERM_MEMORY_MODEL: str = "gpt-5-nano"
    LONG_TERM_MEMORY_EMBEDDER_MODEL: str = "text-embedding-3-small"
    LONG_TERM_MEMORY_COLLECTION_NAME: str = "longterm_memory"

    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    # Access tokens are short-lived because they cannot be revoked cheaply; the
    # long-lived, revocable credential is the refresh token below.
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    LOG_DIR: Path = Path("logs")
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    PROFILING_DIR: Path = Path("/tmp/fastapi_profiles")
    PROFILING_THRESHOLD_SECONDS: float = 2.0

    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "pt_db"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_POOL_SIZE: int = 20
    POSTGRES_MAX_OVERFLOW: int = 10
    # Escape hatch that takes precedence over the POSTGRES_* parts above. Exists so
    # tests and smoke runs can point at SQLite without inventing a fake Postgres.
    #
    # Deliberately not named DATABASE_URL: .env.example already defines that for
    # the old src/ flow as a bare `postgresql://` DSN, which SQLAlchemy would
    # route to the psycopg2 driver this project does not install.
    AUTH_DATABASE_URL: str = ""
    CHECKPOINT_TABLES: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["checkpoint_blobs", "checkpoint_writes", "checkpoints"]
    )

    VALKEY_HOST: str = ""
    VALKEY_PORT: int = 6379
    VALKEY_DB: int = 0
    VALKEY_PASSWORD: str = ""
    VALKEY_MAX_CONNECTIONS: int = 20
    CACHE_TTL_SECONDS: int = 60

    RATE_LIMIT_DEFAULT: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["200 per day", "50 per hour"]
    )
    RATE_LIMIT_ENDPOINTS: Annotated[dict[str, list[str]], NoDecode] = Field(
        default_factory=lambda: _DEFAULT_RATE_LIMIT_ENDPOINTS.copy()
    )

    EVALUATION_LLM: str = "gpt-5"
    EVALUATION_BASE_URL: str = "https://api.openai.com/v1"
    EVALUATION_API_KEY: str = ""
    EVALUATION_SLEEP_TIME: int = 10

    @field_validator("ALLOWED_ORIGINS", "RATE_LIMIT_DEFAULT", "CHECKPOINT_TABLES", mode="before")
    @classmethod
    def parse_list_fields(cls, value: Any) -> list[str]:
        """Parse comma-separated env strings into list[str]."""
        if isinstance(value, list):
            return value
        parsed = _parse_csv_list(value)
        return parsed

    @property
    def sqlalchemy_database_uri(self) -> str:
        """SQLAlchemy URL for the auth tables.

        Returns AUTH_DATABASE_URL when set, otherwise assembles a psycopg3
        Postgres URL from the POSTGRES_* parts. A bare ``postgresql://`` override
        is rewritten to name psycopg3 explicitly, since SQLAlchemy would
        otherwise default to psycopg2, which is not a dependency of this project.
        """
        if self.AUTH_DATABASE_URL:
            if self.AUTH_DATABASE_URL.startswith("postgresql://"):
                return self.AUTH_DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
            return self.AUTH_DATABASE_URL
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    def validate_auth_secrets(self) -> None:
        """Reject a signing key that is missing or too short to be meaningful.

        Called from the app's lifespan rather than from the model validator, so
        that importing settings (in tooling, Alembic, or a test collection pass)
        does not require a production secret to be present.

        Raises:
            RuntimeError: If JWT_SECRET_KEY is unset or under 32 characters.
        """
        if not self.JWT_SECRET_KEY or len(self.JWT_SECRET_KEY) < 32:
            raise RuntimeError(
                "JWT_SECRET_KEY must be set and at least 32 characters. "
                "Generate one with: openssl rand -hex 32"
            )

    def apply_environment_settings(self) -> None:
        """Apply environment-specific settings based on the current environment."""
        env_settings = {
            Environment.DEVELOPMENT: {
                "DEBUG": True,
                "LOG_LEVEL": "DEBUG",
                "LOG_FORMAT": "console",
                "RATE_LIMIT_DEFAULT": ["1000 per day", "200 per hour"],
            },
            Environment.STAGING: {
                "DEBUG": False,
                "LOG_LEVEL": "INFO",
                "RATE_LIMIT_DEFAULT": ["500 per day", "100 per hour"],
            },
            Environment.PRODUCTION: {
                "DEBUG": False,
                "LOG_LEVEL": "WARNING",
                "RATE_LIMIT_DEFAULT": ["200 per day", "50 per hour"],
            },
        }
        current_env_settings = env_settings.get(self.ENVIRONMENT, {})
        for key, value in current_env_settings.items():
            if key.upper() not in os.environ:
                object.__setattr__(self, key, value)

    @model_validator(mode="after")
    def finalize_settings(self) -> "Settings":
        """Apply derived defaults, rate-limit endpoint overrides, and env presets."""
        endpoints = dict(self.RATE_LIMIT_ENDPOINTS)
        for endpoint in _DEFAULT_RATE_LIMIT_ENDPOINTS:
            env_key = f"RATE_LIMIT_{endpoint.upper()}"
            value = parse_list_from_env(env_key)
            if value:
                endpoints[endpoint] = value
        object.__setattr__(self, "RATE_LIMIT_ENDPOINTS", endpoints)
        if not self.EVALUATION_API_KEY:
            object.__setattr__(self, "EVALUATION_API_KEY", self.OPENAI_API_KEY)
        self.apply_environment_settings()
        return self


settings = Settings()
