from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import Field, PostgresDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
# Runtime artifacts live outside src/ so the source tree stays immutable at
# runtime -- required for read-only container filesystems and reproducible
# builds. Override with WORKSPACE_ROOT; relative values resolve against
# _PROJECT_ROOT (see resolve_workspace_root).
_DEFAULT_WORKSPACE = _PROJECT_ROOT / "var" / "workspace"
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
    # does not affect production; see verification_production_use_real_ragas
    # for that gate. See known_limitations_remediation_plan.md, L1.
    verification_use_real_ragas: bool = True

    # Phase 3 of the L1 remediation: gates whether verification/executor.py's
    # production path scores faithfulness with the real Ragas SDK instead of
    # the heuristic proxy. Deliberately a *separate* flag from
    # verification_use_real_ragas above -- that one only ever affected the
    # offline benchmark (zero production blast radius); this one changes real
    # request latency/cost for every build_plan/edit_plan call. Off by
    # default; on in this repo's local .env as of 2026-07-30 following Phase
    # 0's baseline (100% false-negative rate on the adversarial taxonomy) and
    # a real-dev-environment shadow-eval run that found a genuine citation
    # mismatch in production-shaped data. On failure (rate limit already
    # exceeded, API error, SDK error), evaluate_faithfulness falls back to the
    # heuristic for that call rather than failing the request.
    verification_production_use_real_ragas: bool = False

    # Shadow evaluation (Phase 2 of the L1 remediation): a periodic background
    # task scores recently-completed runs with the real Ragas SDK and logs the
    # result to LangFuse, without touching the synchronous request path.
    # Independent of verification_production_use_real_ragas above -- shadow
    # eval can run whether or not production itself gates on the real score.
    # Off by default -- opt-in until Phase 0's baseline numbers justify enabling it.
    verification_shadow_eval_enabled: bool = False
    verification_shadow_eval_interval_seconds: float = 300.0
    # Fraction of eligible completed runs to score per tick (cost control at
    # scale) -- 1.0 scores every eligible run, matching current low traffic.
    verification_shadow_eval_sample_rate: float = 1.0
    # Cap per tick so one run of the periodic task can't take unbounded time /
    # cost if a large backlog of unscored runs ever accumulates.
    verification_shadow_eval_batch_size: int = 20

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

    # Local fitness knowledge base (retrieval tuning -- storage moved to Fitness MCP Server)
    local_kb_enabled: bool = True
    local_kb_top_k: int = 3
    local_kb_min_documents: int = 1
    local_kb_min_trust_score: float = 0.85

    # Fitness MCP Server (own process: `uv run python -m core.mcp.fitness_server`;
    # sole owner of guideline documents + workout templates, backed by Postgres + pgvector)
    fitness_mcp_host: str = "127.0.0.1"
    fitness_mcp_port: int = 8100
    fitness_mcp_tool_timeout_seconds: float = 20.0
    # Set true to skip the real Fitness MCP server/Postgres and use an in-memory dev double
    mock_fitness_kb: bool = False
    fitness_kb_embedding_model: str = "text-embedding-3-small"
    # Measured against the real ingested corpus (text-embedding-3-small): genuinely
    # correct matches for realistic queries score 0.5-0.78 cosine similarity, not
    # near 1.0 -- this model's embedding space isn't calibrated that way for short
    # text. 0.75 (an unvalidated guess) returned zero hits for 2 of 3 realistic test
    # queries despite an obviously correct match existing. 0.4 keeps genuine matches
    # while still filtering clearly unrelated content (which drops to ~0.35-0.45).
    fitness_kb_min_similarity: float = 0.4
    fitness_kb_chunk_max_chars: int = 2000
    fitness_kb_chunk_overlap: int = 200
    # Hybrid RAG retrieval tuning (rewrite → dense+keyword RRF pool → rerank → top-k)
    fitness_kb_candidate_pool: int = 50
    fitness_kb_rrf_k: int = 60
    fitness_kb_query_rewrite_enabled: bool = True
    fitness_kb_rerank_enabled: bool = True

    # Hybrid Supervisor routing: the Supervisor node proposes the next capability
    # via an LLM judge (core.agents.supervisor_router_judge) and a deterministic
    # Policy Engine (core.capabilities.policy_engine) validates/overrides that
    # proposal before routing. supervisor_max_hops is the loop-prevention guardrail.
    supervisor_max_hops: int = 12

    # L1 Phase 4: how many times a failed Verification result may automatically
    # route back to whichever capability owns the failing check (research for
    # citation/faithfulness, fitness for consistency/safety) before falling
    # through to HITL regardless. Separate from MAX_REVISION_COUNT
    # (core/hitl/resume.py), which caps *human*-requested revisions -- this
    # caps the *automatic* retry the Policy Engine triggers on its own.
    # supervisor_max_hops remains the backstop for both.
    max_verification_retry_attempts: int = 1

    # Wall-clock deadline for a single graph.invoke() call (background run
    # execution, resume, continue, and profile-form resume). Bounds a run
    # even if a node hangs on something with no timeout of its own.
    run_execution_timeout_seconds: float = 900.0

    # How often the background orphan-reconciliation sweep runs while the API
    # process is up (in addition to the one that always runs at startup).
    reconciliation_interval_seconds: float = 300.0

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
    # "json" for machine-parseable production logs, "text" for readable local
    # output. Applied by core.observability.logging.configure_logging.
    log_format: str = "json"

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
