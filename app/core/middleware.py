"""Cross-cutting request middleware."""

from collections.abc import Callable
from typing import override

from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.configs.config import settings
from app.core.logging import bind_context, clear_context


class LoggingContextMiddleware(BaseHTTPMiddleware):
    """Bind token claims to the log context for the duration of a request.

    Best-effort only. It does not assert scope and never rejects a request: the
    auth dependency is the single authority on whether a token is acceptable.
    Duplicating that judgement here would mean two places to keep in sync, and a
    middleware 401 would bypass the ``WWW-Authenticate`` handling the endpoints
    do.
    """

    @override
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Extract claims into the logging context, then always clear them."""
        clear_context()
        try:
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                try:
                    payload = jwt.decode(
                        auth_header.removeprefix("Bearer ").strip(),
                        settings.JWT_SECRET_KEY,
                        algorithms=[settings.JWT_ALGORITHM],
                    )
                except JWTError:
                    pass  # the auth dependency will produce the 401
                else:
                    if payload.get("typ") == "session":
                        bind_context(session_id=payload.get("sub"))
                    if payload.get("uid") is not None:
                        bind_context(user_id=payload.get("uid"))
            return await call_next(request)
        finally:
            # Workers are reused across requests; leaving context bound would
            # attribute the next caller's log lines to this user.
            clear_context()
