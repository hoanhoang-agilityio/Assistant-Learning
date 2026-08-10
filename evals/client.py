"""The Langfuse client the evaluation run writes scores with."""

from langfuse import Langfuse

from app.core.configs.config import settings


def build_client() -> Langfuse:
    """Build a Langfuse client configured as a score *writer*.

    Returns:
        A client scoped to this environment, verified able to write.

    Raises:
        RuntimeError: When the client came up with tracing disabled. The SDK
            computes ``tracing_enabled and os.environ[LANGFUSE_TRACING_ENABLED]
            != "false"`` — an ``and``, so an env carrying ``false`` (which
            ``.env.example`` ships) wins over the kwarg below. Every score
            method then opens with ``if not self._tracing_enabled: return``, and
            a whole judged run reports success having written nothing. Checking
            here turns that silent no-op into a startup error.
    """
    client = Langfuse(
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        secret_key=settings.LANGFUSE_SECRET_KEY,
        # Self-hosted: without an explicit host the client talks to Langfuse
        # Cloud and finds none of these traces.
        host=settings.LANGFUSE_HOST,
        environment=settings.ENVIRONMENT.value,
        # Unrelated to whether the *app* traces — this client only writes scores.
        tracing_enabled=True,
        timeout=60,
    )
    if not client._tracing_enabled:
        raise RuntimeError(
            "langfuse_client_disabled_scores_would_be_dropped: "
            "unset LANGFUSE_TRACING_ENABLED=false in the environment running evals"
        )
    return client


__all__ = ["build_client"]
