from __future__ import annotations


class RateLimitExceededError(Exception):
    """Raised when a per-user request, token, or cost cap is exceeded."""

    def __init__(
        self,
        *,
        user_id: str,
        limit_type: str,
        limit_value: int | float,
        current_value: int | float,
        message: str | None = None,
    ) -> None:
        self.user_id = user_id
        self.limit_type = limit_type
        self.limit_value = limit_value
        self.current_value = current_value
        detail = message or (
            f"Rate limit exceeded for user '{user_id}': "
            f"{limit_type} {current_value} >= {limit_value}"
        )
        super().__init__(detail)
