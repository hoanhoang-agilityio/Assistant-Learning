"""Application configuration management.

Environment detection, ``.env`` file resolution and configuration parsing via
pydantic-settings. This module is the only place in the application allowed to read
the process environment.
"""

import os
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

from dotenv import load_dotenv
from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Environment(StrEnum):
    """Application environment types."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class GuardScanner(StrEnum):
    """Input scanners the ``guard_input`` node may run."""

    INVISIBLE_TEXT = "invisible_text"
    BAN_SUBSTRINGS = "ban_substrings"
    REGEX = "regex"
    SECRETS = "secrets"
    TOKEN_LIMIT = "token_limit"
    PROMPT_INJECTION = "prompt_injection"
    TOXICITY = "toxicity"
    BAN_TOPICS = "ban_topics"


class PersistenceBackend(StrEnum):
    """Which storage backs the graph's checkpointer and long-term store.

    Attributes:
        POSTGRES: Durable. The only backend that survives a restart, so the only one an
            ``interrupt()`` gate can be trusted to resume from.
        MEMORY: In-process. Tests and database-free local runs.
    """

    POSTGRES = "postgres"
    MEMORY = "memory"


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

# Also push the resolved file into ``os.environ``, which pydantic-settings does not do.
# Two things below read the process environment directly and would otherwise never see a
# value that lives only in the env file: the per-endpoint ``RATE_LIMIT_*`` overrides, and
# the "was this set explicitly?" check that stops an environment preset from overwriting
# it. ``load_dotenv`` never overrides a variable that is already set, so a real
# environment variable still wins over the file.
if ENV_FILE:
    load_dotenv(ENV_FILE, override=False)


def _parse_csv_list(value: Any) -> Any:
    """Normalize a CSV string or list value for pydantic field validators."""
    if isinstance(value, list):
        return value
    if not isinstance(value, str):
        return value
    return [item.strip().strip("\"'") for item in value.split(",") if item.strip()]


# Shorter than this and an HS256 key has less entropy than the digest it keys.
_MIN_JWT_SECRET_LENGTH = 32

_DEFAULT_RATE_LIMIT_ENDPOINTS: dict[str, list[str]] = {
    "chat": ["30 per minute"],
    "chat_stream": ["20 per minute"],
    "messages": ["50 per minute"],
    "resume": ["30 per minute"],
    # Auth endpoints are keyed on client IP, which is the only identity that
    # exists before a login succeeds — so these are what stand between the
    # service and credential stuffing.
    "register": ["10 per hour"],
    "login": ["20 per minute"],
    "refresh": ["30 per hour"],
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
    ALLOWED_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["*"]
    )

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
    DEFAULT_LLM_MODEL: str = "gpt-5-mini"
    DEFAULT_LLM_TEMPERATURE: float = 0.2
    MAX_TOKENS: int = 2000
    COACH_MAX_TOKENS: int = 8000
    QA_MAX_TOKENS: int = 2000
    HISTORY_MAX_TOKENS: int = 4000
    # Attempts, not retries: 3 means one call and two more if the first two fail with
    # something transient. The agent middleware takes retries-after-the-first, so it is
    # handed this minus one.
    MAX_LLM_CALL_RETRIES: int = 3
    # Retries after the first tool call. A tool failure is handed back to the model as a
    # tool message once the budget is spent, so the agent can recover rather than die.
    TOOL_MAX_RETRIES: int = 2
    # A bound on the agent's own tool loop, so a model that keeps calling tools without
    # answering costs a finite number of inferences rather than the whole rate limit.
    AGENT_MAX_MODEL_CALLS: int = 25
    LLM_TOTAL_TIMEOUT: int = 60

    # --- Input guard (spec §1 `guard_input`, §9 "Guard failure → Block request") --------
    GUARD_ENABLED: bool = True
    GUARD_SCANNERS: Annotated[list[GuardScanner], NoDecode] = Field(
        default_factory=lambda: list(GuardScanner)
    )
    # Stop at the first rejection. The scanners are ordered cheapest-first, so this is
    # also what keeps a banned substring from costing two model inferences.
    GUARD_FAIL_FAST: bool = True
    GUARD_USE_ONNX: bool = False
    GUARD_MAX_INPUT_TOKENS: int = 2048
    # No default wordlist or pattern set: both are deployment policy, and a scanner with
    # nothing to match on is skipped rather than constructed empty.
    GUARD_BANNED_SUBSTRINGS: Annotated[list[str], NoDecode] = Field(
        default_factory=list
    )
    GUARD_BANNED_PATTERNS: Annotated[list[str], NoDecode] = Field(default_factory=list)
    GUARD_BANNED_TOPICS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["violence", "self-harm", "weapons", "illegal drugs"]
    )
    GUARD_PROMPT_INJECTION_THRESHOLD: float = 0.92
    GUARD_TOXICITY_THRESHOLD: float = 0.5
    GUARD_BANNED_TOPICS_THRESHOLD: float = 0.6

    # --- Graph retry limits (spec §9: every limit is a counter in GraphState) ---------
    USER_INFO_MAX_RETRIES: int = 3
    COACH_MAX_RETRIES: int = 3
    HITL_MAX_RETRIES: int = 3
    QA_MAX_RETRIES: int = 3

    # --- Knowledge base / RAG (spec §8) ----------------------------------------------
    KNOWLEDGE_EMBEDDER_MODEL: str = "text-embedding-3-small"
    KNOWLEDGE_EMBEDDING_DIM: int = 1536
    KNOWLEDGE_TOP_K: int = 4
    KNOWLEDGE_MIN_SCORE: float = 0.3
    KNOWLEDGE_MAX_OVERLAP: float = 0.8
    FAITHFULNESS_THRESHOLD: float = 0.9
    # RAGAS defaults to 1024, which a reasoning model spends on reasoning tokens before
    # it emits the structured verdict, and a truncated verdict scores nothing.
    RAGAS_MAX_TOKENS: int = 4096

    # --- Authentication --------------------------------------------------------------
    # No default for the signing key: a fallback would let the service boot in
    # production signing tokens anyone who has read the source can forge.
    # Checked by ``validate_auth_secrets`` at startup, not here, so importing
    # settings from Alembic or a test collection pass does not need a secret.
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    # Access tokens are short-lived because revoking one costs a denylist row and
    # a read per request; the long-lived revocable credential is the refresh
    # token below.
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # --- Persistence -----------------------------------------------------------------
    PERSISTENCE_BACKEND: PersistenceBackend = PersistenceBackend.POSTGRES

    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "coaching_db"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_POOL_SIZE: int = 20
    POSTGRES_MAX_OVERFLOW: int = 10
    DATABASE_URL: str = ""

    # --- Rate limiting ---------------------------------------------------------------
    RATE_LIMIT_DEFAULT: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["200 per day", "50 per hour"]
    )
    RATE_LIMIT_ENDPOINTS: dict[str, list[str]] = Field(
        default_factory=_DEFAULT_RATE_LIMIT_ENDPOINTS.copy
    )

    # --- Logging ---------------------------------------------------------------------
    LOG_DIR: Path = Path("logs")
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    @field_validator(
        "ALLOWED_ORIGINS",
        "RATE_LIMIT_DEFAULT",
        "GUARD_SCANNERS",
        "GUARD_BANNED_SUBSTRINGS",
        "GUARD_BANNED_PATTERNS",
        "GUARD_BANNED_TOPICS",
        mode="before",
    )
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
                return self.DATABASE_URL.replace(
                    "postgresql://", "postgresql+psycopg://", 1
                )
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
        return self.sqlalchemy_database_uri.replace(
            "postgresql+psycopg://", "postgresql://", 1
        )

    def validate_auth_secrets(self) -> None:
        """Reject a signing key that is missing or too short to be meaningful.

        Called from the application lifespan rather than from a model validator, so
        that importing settings — in Alembic, tooling, or a test collection pass —
        does not require a production secret to be present.

        Raises:
            RuntimeError: If ``JWT_SECRET_KEY`` is unset or under 32 characters.
        """
        if not self.JWT_SECRET_KEY or len(self.JWT_SECRET_KEY) < _MIN_JWT_SECRET_LENGTH:
            raise RuntimeError(
                f"JWT_SECRET_KEY must be set and at least {_MIN_JWT_SECRET_LENGTH} "
                "characters. Generate one with: openssl rand -hex 32"
            )

    @model_validator(mode="after")
    def apply_environment_settings(self) -> "Settings":
        """Apply per-endpoint rate limits and environment presets over loaded values."""
        endpoints = dict(self.RATE_LIMIT_ENDPOINTS)
        for endpoint in _DEFAULT_RATE_LIMIT_ENDPOINTS:
            override = os.getenv(f"RATE_LIMIT_{endpoint.upper()}")
            if override:
                endpoints[endpoint] = _parse_csv_list(override)
        object.__setattr__(self, "RATE_LIMIT_ENDPOINTS", endpoints)

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
