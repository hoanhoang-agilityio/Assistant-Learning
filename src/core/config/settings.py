from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import Field, PostgresDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_WORKSPACE = _PROJECT_ROOT / "src" / "workspace"
_ENV_FILE = _PROJECT_ROOT / ".env"

# pydantic-settings only maps known fields onto Settings; SDKs such as LangSmith
# read LANGSMITH_* from os.environ directly. Load .env into the process env so
# those vars are visible even when they are not Settings fields.
load_dotenv(_ENV_FILE, override=False)


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
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

    # Production API state — Postgres-backed by default so run checkpoints and
    # per-user rate-limit counters survive restarts and are shared across
    # horizontally scaled replicas. Set to false only for local/dev/CI runs
    # without a reachable Postgres instance.
    use_postgres_checkpointer: bool = True
    use_postgres_rate_limit_store: bool = True

    # LLM — Reasoning Sandwich tiers (defaults favor lower-cost models)
    openai_api_key: str | None = None
    openai_standard_model: str = "gpt-5.4-mini"
    openai_xhigh_model: str = "gpt-5.4"
    openai_standard_reasoning_effort: str | None = "none"
    openai_xhigh_reasoning_effort: str | None = "low"
    openai_verbosity: str | None = "low"
    anthropic_api_key: str | None = None
    anthropic_xhigh_model: str = "claude-3-5-haiku-20241022"
    openai_max_tokens: int = 4096
    anthropic_max_tokens: int = 4096
    llm_structured_output_max_tokens: int = 2048
    # Per-call deadlines (SDK-native `timeout=` kwarg) so a hung provider
    # connection can never block a run indefinitely.
    openai_standard_timeout_seconds: float = 60.0
    openai_xhigh_timeout_seconds: float = 90.0
    anthropic_timeout_seconds: float = 90.0

    # Off by default: when true, core.evaluation.ragas_benchmark's
    # evaluate_draft_faithfulness scores drafts with the real Ragas SDK
    # (core.evaluation.ragas) instead of the heuristic proxy
    # (verification.utils.heuristic_faithfulness_data). Benchmark-only --
    # production's _ragas_faithfulness_node always uses the heuristic
    # regardless of this flag. See known_limitations_remediation_plan.md, L1.
    verification_use_real_ragas: bool = False

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
    # Deadline for each Tavily MCP call (tool handshake, search, extract).
    tavily_tool_timeout_seconds: float = 20.0

    # Research Agent
    research_max_search_iterations: int = 2
    research_max_total_searches: int = 3
    research_max_total_extracts: int = 5
    research_extract_top_k: int = 8
    research_trusted_domains: str = ""
    research_tool_content_preview_chars: int = 250
    research_synthesis_evidence_limit: int = 5
    research_synthesis_content_chars: int = 800
    research_min_verified_sources_for_skip_eval: int = 2
    research_min_evidence_docs_for_skip_eval: int = 1
    research_query_cache_ttl_seconds: int = 3600

    # Local fitness knowledge base
    local_kb_enabled: bool = True
    local_kb_path: str = ""
    local_kb_top_k: int = 3
    local_kb_min_documents: int = 1
    local_kb_min_trust_score: float = 0.85

    # Orchestration / Fitness retry budgets
    max_planner_attempts: int = 2
    fix_reasoning_planner_attempts: int = 1

    # Wall-clock deadline for a single graph.invoke() call (background run
    # execution, resume, continue, and profile-form resume). Bounds a run
    # even if a node hangs on something with no timeout of its own.
    run_execution_timeout_seconds: float = 900.0

    # How often the background orphan-reconciliation sweep runs while the API
    # process is up (in addition to the one that always runs at startup).
    reconciliation_interval_seconds: float = 300.0

    classify_request_narrows_domains: bool = True

    run_execution_plan_enabled: bool = True

    verify_workflow_enabled: bool = True

    edit_workflow_v2_enabled: bool = True

    # LLM payload observability (debug only; does not change business logic)
    llm_payload_debug: bool = False

    # Per-user AI rate limits (UTC day buckets)
    rate_limit_enabled: bool = True
    rate_limit_default_user_id: str = "anonymous"
    rate_limit_daily_max_requests_per_user: int = 20
    rate_limit_daily_max_tokens_per_user: int = 200_000
    rate_limit_daily_max_cost_usd_per_user: float = 2.0

    # App
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

    @field_validator("rate_limit_enabled", mode="before")
    @classmethod
    def parse_rate_limit_enabled(cls, value: object) -> bool:
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
