"""Unit tests for the auth primitives: token scoping, hashing, and password rules.

No database and no HTTP. These are the assertions that make the two token types a real
privilege boundary rather than decoration — ``test_session_token_rejected_as_user_token``
is what fails if the ``typ`` check in ``decode_token`` is ever dropped.
"""

from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt

from src.core.configs.config import settings
from src.models.user import User
from src.schemas.auth import UserCreate
from src.utils.auth import (
    InvalidTokenError,
    TokenType,
    create_access_token,
    decode_token,
    generate_refresh_token,
    hash_refresh_token,
)
from src.utils.sanitization import sanitize_email, validate_password_strength

PASSWORD = "Secret123!"  # noqa: S105 — test fixture value, not a credential


# ------------------------------------------------------------------ token scope


def test_user_token_round_trips() -> None:
    """A user token decodes back to its subject under the USER scope."""
    token = create_access_token("42", TokenType.USER)
    payload = decode_token(token.access_token, TokenType.USER)

    assert payload["sub"] == "42"
    assert payload["typ"] == "user"
    assert payload["jti"]


def test_session_token_carries_owner() -> None:
    """A session token records the owner so ownership can be re-checked on use."""
    token = create_access_token("sess-1", TokenType.SESSION, user_id=7)
    payload = decode_token(token.access_token, TokenType.SESSION)

    assert payload["sub"] == "sess-1"
    assert payload["uid"] == 7


def test_session_token_requires_owner() -> None:
    """Minting a session token without a uid is a programming error, not a silent gap."""
    with pytest.raises(ValueError, match="user_id is required"):
        create_access_token("sess-1", TokenType.SESSION)


def test_session_token_rejected_as_user_token() -> None:
    """The scope check: a session token must not satisfy a user-scoped decode."""
    token = create_access_token("sess-1", TokenType.SESSION, user_id=7)

    with pytest.raises(InvalidTokenError, match="not valid for this operation"):
        decode_token(token.access_token, TokenType.USER)


def test_user_token_rejected_as_session_token() -> None:
    """And the reverse direction."""
    token = create_access_token("42", TokenType.USER)

    with pytest.raises(InvalidTokenError, match="not valid for this operation"):
        decode_token(token.access_token, TokenType.SESSION)


# ------------------------------------------------------------- malformed tokens


@pytest.mark.parametrize("token", ["", "not-a-jwt", "a.b.c"])
def test_structurally_invalid_tokens_rejected(token: str) -> None:
    """Garbage in the Authorization header is an auth failure, never a crash."""
    with pytest.raises(InvalidTokenError):
        decode_token(token, TokenType.USER)


def test_tampered_signature_rejected() -> None:
    """Mutating a single character invalidates the signature."""
    token = create_access_token("42", TokenType.USER)

    with pytest.raises(InvalidTokenError):
        decode_token(token.access_token + "x", TokenType.USER)


def test_expired_token_rejected() -> None:
    """Expiry is enforced on decode, not merely advertised in the payload."""
    token = create_access_token(
        "42", TokenType.USER, expires_delta=timedelta(seconds=-1)
    )

    with pytest.raises(InvalidTokenError):
        decode_token(token.access_token, TokenType.USER)


def test_token_without_jti_rejected() -> None:
    """A token that cannot be denylisted is not accepted, however well it is signed."""
    forged = jwt.encode(
        {
            "sub": "42",
            "typ": "user",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    with pytest.raises(InvalidTokenError, match="missing a jti"):
        decode_token(forged, TokenType.USER)


def test_token_signed_with_another_key_rejected() -> None:
    """Only this service's signing key produces an acceptable token."""
    forged = jwt.encode(
        {
            "sub": "42",
            "typ": "user",
            "jti": "x",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        "a-different-secret-that-is-also-long-enough",
        algorithm=settings.JWT_ALGORITHM,
    )

    with pytest.raises(InvalidTokenError):
        decode_token(forged, TokenType.USER)


def test_jti_is_unique_per_token() -> None:
    """Two tokens for the same subject are independently revocable."""
    first = decode_token(
        create_access_token("42", TokenType.USER).access_token, TokenType.USER
    )
    second = decode_token(
        create_access_token("42", TokenType.USER).access_token, TokenType.USER
    )

    assert first["jti"] != second["jti"]


# ------------------------------------------------------------- refresh tokens


def test_refresh_token_is_hashed_before_storage() -> None:
    """What is handed to the client and what is stored are never the same string."""
    raw, token_hash, expires_at = generate_refresh_token()

    assert raw != token_hash
    assert len(token_hash) == 64
    assert token_hash == hash_refresh_token(raw)
    assert expires_at > datetime.now(UTC)


def test_refresh_tokens_are_unique() -> None:
    """Each call mints fresh entropy."""
    assert generate_refresh_token()[0] != generate_refresh_token()[0]


# ------------------------------------------------------------------- passwords


def test_password_hash_verifies() -> None:
    """A bcrypt hash round-trips and never contains the plaintext."""
    hashed = User.hash_password(PASSWORD)
    user = User(email="a@example.com", hashed_password=hashed)

    assert hashed.startswith("$2b$")
    assert PASSWORD not in hashed
    assert user.verify_password(PASSWORD)
    assert not user.verify_password("Wrong123!")


def test_password_over_bcrypt_limit_rejected() -> None:
    """Past 72 bytes bcrypt ignores the rest, so the extra length must not be accepted."""
    with pytest.raises(ValueError, match="72 bytes"):
        User.hash_password("A1!" + "x" * 80)


def test_corrupt_stored_hash_is_a_failure_not_a_crash() -> None:
    """A malformed hash column authenticates nobody and raises nothing."""
    user = User(email="a@example.com", hashed_password="not-a-bcrypt-hash")

    assert not user.verify_password(PASSWORD)


@pytest.mark.parametrize(
    ("password", "rule"),
    [
        ("Ab1!", "at least 8"),
        ("nouppercase1!", "uppercase"),
        ("NOLOWERCASE1!", "lowercase"),
        ("NoDigitsHere!", "number"),
        ("NoSpecial123", "special"),
    ],
)
def test_password_rules_are_enforced_individually(password: str, rule: str) -> None:
    """Each rule fails with its own message rather than one generic rejection."""
    with pytest.raises(ValueError, match=rule):
        validate_password_strength(password)


def test_registration_schema_applies_the_same_rules() -> None:
    """``UserCreate`` delegates to the shared validator, so the two cannot drift."""
    with pytest.raises(ValueError, match="uppercase"):
        UserCreate(email="a@example.com", password="nouppercase1!")


def test_password_is_not_exposed_by_the_schema() -> None:
    """``SecretStr`` keeps the plaintext out of reprs and accidental log lines."""
    payload = UserCreate(email="a@example.com", password=PASSWORD)

    assert PASSWORD not in repr(payload)
    assert payload.password.get_secret_value() == PASSWORD


# ---------------------------------------------------------------- sanitization


def test_email_is_normalized() -> None:
    """Lookup keys are lowercased so one address cannot register twice."""
    assert sanitize_email("User@Example.COM") == "user@example.com"


@pytest.mark.parametrize("value", ["not-an-email", "a@b", "@example.com", ""])
def test_invalid_emails_rejected(value: str) -> None:
    """Anything that is not an address raises rather than reaching the database."""
    with pytest.raises(ValueError, match="Invalid email format"):
        sanitize_email(value)
