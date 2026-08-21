"""Authentication request and response schemas."""

import re
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, SecretStr, field_validator

from app.schemas.base import BaseResponse
from app.utils.sanitization import validate_password_strength

_UNSAFE_NAME_CHARS = re.compile(r"[<>{}\[\]()\'\"`]")


class Token(BaseModel):
    """An issued access token."""

    access_token: str = Field(..., description="The JWT access token")
    token_type: str = Field(default="bearer", description="The type of token")
    expires_at: datetime = Field(..., description="The token expiration timestamp")


class TokenResponse(BaseResponse):
    """Response for login and refresh."""

    access_token: str = Field(..., description="The JWT access token")
    token_type: str = Field(default="bearer", description="The type of token")
    expires_at: datetime = Field(..., description="When the access token expires")
    refresh_token: str = Field(..., description="Opaque refresh credential")
    email: str | None = Field(default=None, description="Account email, when known")
    username: str | None = Field(default=None, description="Optional display name")


class UserCreate(BaseModel):
    """Registration payload."""

    email: EmailStr = Field(..., description="User's email address")
    password: SecretStr = Field(..., description="User's password", min_length=8, max_length=64)
    username: str | None = Field(default=None, description="Optional display name", max_length=50)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: SecretStr) -> SecretStr:
        """Enforce password strength via the shared validator."""
        validate_password_strength(v.get_secret_value())
        return v


class UserResponse(BaseResponse):
    """Response for registration."""

    id: int = Field(..., description="User's ID")
    email: str = Field(..., description="User's email address")
    username: str | None = Field(default=None, description="Optional display name")
    token: Token = Field(..., description="User-scoped access token")
    refresh_token: str = Field(..., description="Opaque refresh credential")


class SessionResponse(BaseResponse):
    """Response for session create, rename, and list."""

    session_id: str = Field(..., description="The unique identifier for the session")
    name: str = Field(default="", description="Name of the session", max_length=100)
    token: Token = Field(..., description="Session-scoped access token")

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        """Strip characters that could break downstream rendering."""
        return _UNSAFE_NAME_CHARS.sub("", v)
