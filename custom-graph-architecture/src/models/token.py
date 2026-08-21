"""Refresh-token and revocation models."""

from datetime import datetime

from sqlmodel import Field

from src.models.base import BaseModel


class RefreshToken(BaseModel, table=True):
    """A hashed, revocable refresh credential.

    Only the SHA-256 hash is stored, so a database leak does not yield tokens an
    attacker can present. ``revoked_at`` is set on use (rotation) and on logout.
    """

    __tablename__ = "refresh_token"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    token_hash: str = Field(unique=True, index=True)
    expires_at: datetime
    revoked_at: datetime | None = Field(default=None)


class RevokedToken(BaseModel, table=True):
    """Denylist of access-token JTIs invalidated before their natural expiry.

    Rows are only useful until ``expires_at``, after which the token fails expiry
    validation anyway — see ``AuthService.purge_expired_tokens``.
    """

    __tablename__ = "revoked_token"

    jti: str = Field(primary_key=True)
    expires_at: datetime = Field(index=True)
