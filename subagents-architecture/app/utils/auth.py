"""JWT creation and verification.

Four rules this module exists to enforce:

1. A bearer token is never sanitized or HTML-escaped before decoding. A JWT is
   base64url; escaping is a no-op at best and corrupts the signature check at
   worst, while hiding real failures behind a generic 422.
2. Every decode asserts the expected ``typ``. Without that check a session token
   would be accepted wherever a user token is required and the privilege split
   between the two scopes would be decorative.
3. Every access token carries a ``jti`` so it can be denylisted at logout.
4. Session tokens carry ``uid`` so the session's owner can be re-verified
   against the token instead of trusted from the row alone.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from jose import JWTError, jwt

from app.core.configs.config import settings
from app.core.logging import logger
from app.schemas.auth import Token

_JTI_BYTES = 16
_REFRESH_TOKEN_BYTES = 48


class TokenType(StrEnum):
    """Scope of an issued JWT."""

    USER = "user"
    SESSION = "session"


class InvalidTokenError(Exception):
    """Raised when a token is malformed, expired, or of the wrong scope."""


def _now() -> datetime:
    return datetime.now(UTC)


def create_access_token(
    subject: str,
    token_type: TokenType,
    user_id: int | None = None,
    expires_delta: timedelta | None = None,
) -> Token:
    """Create a signed access token.

    Args:
        subject: User id as a string for USER tokens, session id for SESSION tokens.
        token_type: The scope this token grants.
        user_id: Owner id. Required for SESSION tokens so ownership can be re-checked.
        expires_delta: Optional override for the configured expiry.

    Returns:
        Token: The encoded JWT and its expiry.

    Raises:
        ValueError: If a session token is requested without an owner.
    """
    if token_type is TokenType.SESSION and user_id is None:
        raise ValueError("user_id is required when issuing a session token")

    issued_at = _now()
    expire = issued_at + (
        expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    payload: dict[str, Any] = {
        "sub": subject,
        "typ": token_type.value,
        "iat": issued_at,
        "exp": expire,
        "jti": secrets.token_urlsafe(_JTI_BYTES),
    }
    if user_id is not None:
        payload["uid"] = user_id

    encoded = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    # The jti, not the token, so a leaked log cannot be replayed.
    logger.info(
        "token_created",
        token_type=token_type.value,
        jti=payload["jti"],
        expires_at=expire.isoformat(),
    )
    return Token(access_token=encoded, expires_at=expire)


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    """Decode a token and assert its scope.

    Args:
        token: The raw bearer credential, exactly as received.
        expected_type: The scope the calling endpoint requires.

    Returns:
        dict: The verified claims.

    Raises:
        InvalidTokenError: On any structural, signature, expiry, or scope failure.
    """
    if not token or not isinstance(token, str):
        raise InvalidTokenError("Token must be a non-empty string")

    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require_exp": True, "require_sub": True},
        )
    except JWTError as exc:
        logger.warning("token_verification_failed", error=str(exc))
        raise InvalidTokenError("Could not validate credentials") from exc

    if payload.get("typ") != expected_type.value:
        logger.warning("token_wrong_scope", expected=expected_type.value, actual=payload.get("typ"))
        raise InvalidTokenError("Token is not valid for this operation")

    if not payload.get("jti"):
        raise InvalidTokenError("Token is missing a jti claim")

    return payload


def hash_refresh_token(raw: str) -> str:
    """Hash a refresh token for storage and lookup.

    Plain SHA-256 with no salt is correct here, unlike for passwords: the input
    is 48 bytes of CSPRNG output, so there is no dictionary to attack and lookup
    by hash has to be deterministic.
    """
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_refresh_token() -> tuple[str, str, datetime]:
    """Generate a refresh credential.

    Returns:
        tuple: (plaintext to hand the client, hash to store, expiry).
    """
    raw = secrets.token_urlsafe(_REFRESH_TOKEN_BYTES)
    expires_at = _now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return raw, hash_refresh_token(raw), expires_at
