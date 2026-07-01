from __future__ import annotations

from contextvars import ContextVar, Token

_rate_limit_user_id: ContextVar[str | None] = ContextVar("rate_limit_user_id", default=None)


def set_rate_limit_user_id(user_id: str | None) -> Token[str | None]:
    return _rate_limit_user_id.set(user_id)


def get_rate_limit_user_id() -> str | None:
    return _rate_limit_user_id.get()


def reset_rate_limit_user_id(token: Token[str | None]) -> None:
    _rate_limit_user_id.reset(token)
