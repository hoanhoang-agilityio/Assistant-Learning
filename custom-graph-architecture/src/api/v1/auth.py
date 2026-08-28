"""Authentication and session-authorization endpoints.

Two token scopes, deliberately not interchangeable:

* **User token** (``typ=user``, ``sub=user.id``) — create, list, rename, and delete
  sessions. Also what ``/auth/logout`` accepts.
* **Session token** (``typ=session``, ``sub=session_id``, ``uid=owner``) — scoped to
  exactly one session. This is what conversation endpoints depend on, so a leaked session
  token cannot enumerate the user's other sessions or mint new ones.

The session id doubles as the graph's ``thread_id``, which is what makes
``get_current_session`` the authorization boundary for resuming a checkpointed run.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.configs.config import settings
from src.middlewares import limiter
from src.models.session import Session
from src.models.user import User
from src.schemas.auth import (
    SessionResponse,
    Token,
    TokenResponse,
    UserCreate,
    UserResponse,
)
from src.services.auth import auth_service
from src.utils.auth import (
    InvalidTokenError,
    TokenType,
    create_access_token,
    decode_token,
    generate_refresh_token,
    hash_refresh_token,
)
from src.utils.logging import bind_context, logger
from src.utils.sanitization import sanitize_email, sanitize_string

router = APIRouter()
security = HTTPBearer()

_UNAUTHORIZED = {"WWW-Authenticate": "Bearer"}


async def _reject_if_revoked(payload: dict[str, Any]) -> None:
    """Raise 401 if this token's jti has been denylisted.

    Costs one indexed primary-key read per authenticated request. Move it to Valkey with
    a TTL matching the token expiry if that read becomes hot.
    """
    if await auth_service.is_jti_revoked(payload["jti"]):
        raise HTTPException(
            status_code=401, detail="Token has been revoked", headers=_UNAUTHORIZED
        )


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> User:
    """Resolve the authenticated user from a USER-scoped token.

    Raises:
        HTTPException: 401 if the token is invalid, revoked, or not user-scoped.
    """
    try:
        payload = decode_token(credentials.credentials, TokenType.USER)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=401, detail=str(exc), headers=_UNAUTHORIZED
        ) from exc

    await _reject_if_revoked(payload)

    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=401, detail="Malformed subject claim", headers=_UNAUTHORIZED
        ) from exc

    user = await auth_service.get_user(user_id)
    if user is None:
        # 401 rather than 404: a validly-signed token for a user that no longer exists
        # is an authentication failure, and 404 would confirm which ids are absent to
        # anyone holding an old token.
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials",
            headers=_UNAUTHORIZED,
        )

    bind_context(user_id=user_id)
    return user


async def get_current_session(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> Session:
    """Resolve the authenticated session from a SESSION-scoped token.

    Re-checks that the session still belongs to the ``uid`` in the token, so a session
    that was deleted and its id reused, or reassigned, cannot be reached with the old
    token.

    Raises:
        HTTPException: 401 invalid, revoked, or wrong scope; 403 ownership mismatch;
            404 the session no longer exists.
    """
    try:
        payload = decode_token(credentials.credentials, TokenType.SESSION)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=401, detail=str(exc), headers=_UNAUTHORIZED
        ) from exc

    await _reject_if_revoked(payload)

    session_id = payload["sub"]
    session = await auth_service.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404, detail="Session not found", headers=_UNAUTHORIZED
        )

    if session.user_id != payload.get("uid"):
        raise HTTPException(
            status_code=403, detail="Session does not belong to this user"
        )

    bind_context(user_id=session.user_id, session_id=session_id)
    return session


async def _issue_login_tokens(user_id: int) -> tuple[Token, str]:
    """Mint a user token plus a stored refresh token."""
    token = create_access_token(str(user_id), TokenType.USER)
    raw_refresh, token_hash, refresh_expiry = generate_refresh_token()
    await auth_service.store_refresh_token(user_id, token_hash, refresh_expiry)
    return token, raw_refresh


@router.post(
    "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["register"][0])
async def register_user(request: Request, user_data: UserCreate) -> UserResponse:
    """Create an account and return a user token plus refresh token."""
    try:
        email = sanitize_email(user_data.email)
        username = sanitize_string(user_data.username) if user_data.username else None
        # Hash the secret straight off the model. It is never sanitized: escaping would
        # change what gets hashed and break every password containing characters like
        # & or <.
        hashed = User.hash_password(user_data.password.get_secret_value())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if await auth_service.get_user_by_email(email):
        raise HTTPException(status_code=409, detail="Email already registered")

    user = await auth_service.create_user(
        email=email, password=hashed, username=username
    )
    assert user.id is not None  # assigned by the database on insert
    token, raw_refresh = await _issue_login_tokens(user.id)

    return UserResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        token=token,
        refresh_token=raw_refresh,
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["login"][0])
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    grant_type: str = Form(default="password"),
) -> TokenResponse:
    """Exchange credentials for a user token and refresh token."""
    if grant_type != "password":
        raise HTTPException(
            status_code=400, detail="Unsupported grant type. Must be 'password'"
        )

    # Only the lookup key is normalised. The password is passed through verbatim.
    email = sanitize_string(email).lower()

    user = await auth_service.get_user_by_email(email)
    if user is None or not user.verify_password(password):
        # Identical response for "no such account" and "wrong password", so the endpoint
        # cannot be used to enumerate registered addresses.
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password",
            headers=_UNAUTHORIZED,
        )

    assert user.id is not None
    token, raw_refresh = await _issue_login_tokens(user.id)
    return TokenResponse(
        access_token=token.access_token,
        token_type="bearer",
        expires_at=token.expires_at,
        refresh_token=raw_refresh,
        email=user.email,
        username=user.username,
    )


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["refresh"][0])
async def refresh_access_token(
    request: Request, refresh_token: str = Form(...)
) -> TokenResponse:
    """Rotate a refresh token for a fresh user token.

    Single-use: the presented token is revoked and a new one issued alongside the access
    token.
    """
    user_id = await auth_service.consume_refresh_token(
        hash_refresh_token(refresh_token)
    )
    if user_id is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired refresh token",
            headers=_UNAUTHORIZED,
        )

    user = await auth_service.get_user(user_id)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired refresh token",
            headers=_UNAUTHORIZED,
        )

    token, raw_refresh = await _issue_login_tokens(user_id)
    return TokenResponse(
        access_token=token.access_token,
        token_type="bearer",
        expires_at=token.expires_at,
        refresh_token=raw_refresh,
        email=user.email,
        username=user.username,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> Response:
    """Revoke the presented access token and all of the user's refresh tokens.

    Deliberately not dependent on ``get_current_user``: logging out must work even for a
    user row that has since been deleted.
    """
    try:
        payload = decode_token(credentials.credentials, TokenType.USER)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=401, detail=str(exc), headers=_UNAUTHORIZED
        ) from exc

    await auth_service.revoke_jti(
        payload["jti"], datetime.fromtimestamp(payload["exp"], tz=UTC)
    )
    revoked = await auth_service.revoke_user_refresh_tokens(int(payload["sub"]))
    logger.info(
        "user_logged_out", user_id=payload["sub"], refresh_tokens_revoked=revoked
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/session", response_model=SessionResponse, status_code=status.HTTP_201_CREATED
)
async def create_session(
    user: Annotated[User, Depends(get_current_user)],
) -> SessionResponse:
    """Create a session and return a session-scoped token."""
    assert user.id is not None
    session_id = str(uuid.uuid4())
    session = await auth_service.create_session(
        session_id, user.id, username=user.username
    )
    token = create_access_token(session_id, TokenType.SESSION, user_id=user.id)
    return SessionResponse(session_id=session_id, name=session.name, token=token)


@router.get("/sessions", response_model=list[SessionResponse])
async def get_user_sessions(
    user: Annotated[User, Depends(get_current_user)],
) -> list[SessionResponse]:
    """List the authenticated user's sessions, each with a fresh session token."""
    assert user.id is not None
    sessions = await auth_service.get_user_sessions(user.id)
    return [
        SessionResponse(
            session_id=item.id,
            name=item.name,
            token=create_access_token(item.id, TokenType.SESSION, user_id=user.id),
        )
        for item in sessions
    ]


@router.patch("/session/{session_id}/name", response_model=SessionResponse)
async def update_session_name(
    session_id: str,
    current_session: Annotated[Session, Depends(get_current_session)],
    name: str = Form(...),
) -> SessionResponse:
    """Rename a session. The token must be scoped to that same session."""
    if session_id != current_session.id:
        raise HTTPException(status_code=403, detail="Cannot modify other sessions")

    session = await auth_service.update_session_name(session_id, sanitize_string(name))
    token = create_access_token(
        session_id, TokenType.SESSION, user_id=current_session.user_id
    )
    return SessionResponse(session_id=session_id, name=session.name, token=token)


@router.delete("/session/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    current_session: Annotated[Session, Depends(get_current_session)],
) -> Response:
    """Delete a session."""
    if session_id != current_session.id:
        raise HTTPException(status_code=403, detail="Cannot delete other sessions")

    await auth_service.delete_session(session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
