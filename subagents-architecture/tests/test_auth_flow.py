"""End-to-end assertions for the app/ authentication flow.

Executable form of the auth verification checklist. Runs against a throwaway
SQLite file rather than Postgres, so it needs no running database.

    uv sync && uv run pytest tests/test_auth_flow.py -v

The scope tests (``test_session_token_cannot_create_session`` and
``test_user_token_cannot_reach_session_endpoint``) are the important ones: they
are what makes the two token types a real privilege boundary rather than
decoration. A failure there is a security regression, not a flaky test.
"""

import os
import uuid
from pathlib import Path

import pytest

# Both must be set before app modules are imported: settings is instantiated at
# import time and the engine is built from it.
_DB_PATH = Path(__file__).parent / f"_auth_test_{uuid.uuid4().hex}.db"
os.environ["AUTH_DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
os.environ["JWT_SECRET_KEY"] = "test-only-secret-0123456789abcdef0123456789abcdef"
os.environ["ALLOWED_ORIGINS"] = "http://localhost:3000"

# The limiter keys on client IP, and every test here is the same IP. Production
# allows 10 registrations an hour; this file registers roughly twice that, so
# the defaults turn most of the suite into 429s that look like auth failures.
# Raised through the app's own override rather than by stubbing the limiter, so
# the middleware under test is still the one running.
os.environ["RATE_LIMIT_REGISTER"] = "10000 per hour"
os.environ["RATE_LIMIT_LOGIN"] = "10000 per minute"
os.environ["RATE_LIMIT_REFRESH"] = "10000 per hour"
os.environ["RATE_LIMIT_DEFAULT"] = "100000 per day,100000 per hour"

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

import app.models  # noqa: E402,F401  (registers tables on SQLModel.metadata)
from app.main import app  # noqa: E402
from app.models.database import engine  # noqa: E402

PASSWORD = "Secret123!"  # pragma: allowlist secret

# Only the tables the auth endpoints touch — never the whole metadata.
#
# `SQLModel.metadata` holds every table in the application, and two of them
# (`exercises`, `user_profile`) carry Postgres ARRAY columns SQLite cannot
# compile, so a whole-metadata `create_all` fails here before a test runs.
#
# The second reason is the one that cost a database. The env vars above only
# reach `settings` if this module is the **first** to import `app.*`, and in a
# full-suite run it is not: pytest imports `tests/test_app_*` during collection,
# `settings` is built from `.env`, and `engine` is bound to the developer's
# Postgres before this line is read. A whole-metadata `drop_all` in the teardown
# below then dropped their `user`, `exercises` and `plan_versions` for real.
# Scoping the list is the second line of defence; `_schema` is the first.
_AUTH_TABLE_NAMES = ("user", "session", "refresh_token", "revoked_token")


@pytest.fixture(scope="module", autouse=True)
def _schema():
    """Create the schema directly from the models.

    Deliberately not via Alembic: this asserts the application code is coherent.
    Whether the migration matches the models is a separate question, answered by
    `alembic revision --autogenerate` coming out empty.

    Refuses to touch anything but the throwaway SQLite file. This module issues
    the only DDL in the suite, and it issues it against a module-level `engine`
    it does not own — so "which database am I about to drop tables in" is a
    question it has to answer out loud rather than assume.
    """
    if engine.url.get_backend_name() != "sqlite":
        pytest.fail(
            "refusing to run: `engine` is bound to "
            f"{engine.url.render_as_string(hide_password=True)}, not the throwaway SQLite "
            "file this module sets up. Another test module imported `app.*` first, so "
            "AUTH_DATABASE_URL arrived too late — running on would DROP the tables in that "
            "database. Run this file in its own process:\n"
            "    uv run pytest tests/test_auth_flow.py",
            pytrace=False,
        )

    tables = [SQLModel.metadata.tables[name] for name in _AUTH_TABLE_NAMES]
    SQLModel.metadata.create_all(engine, tables=tables)
    yield
    SQLModel.metadata.drop_all(engine, tables=tables)
    engine.dispose()
    _DB_PATH.unlink(missing_ok=True)


@pytest.fixture(scope="module")
def client():
    """TestClient with the app's lifespan run, so secret validation is exercised."""
    with TestClient(app) as test_client:
        yield test_client


def _unique_email() -> str:
    return f"user-{uuid.uuid4().hex[:12]}@example.com"


@pytest.fixture
def registered(client):
    """A freshly registered user plus their user token and refresh token."""
    email = _unique_email()
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "username": "tester"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return {
        "email": email,
        "user_token": body["token"]["access_token"],
        "refresh_token": body["refresh_token"],
        "id": body["id"],
    }


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _new_session_token(client, user_token: str) -> tuple[str, str]:
    response = client.post("/api/v1/auth/session", headers=_auth(user_token))
    assert response.status_code == 201, response.text
    body = response.json()
    return body["session_id"], body["token"]["access_token"]


# ---------------------------------------------------------------- registration


def test_register_returns_tokens(registered):
    """Check 1: registration yields both an access token and a refresh token."""
    assert registered["user_token"]
    assert registered["refresh_token"]


def test_duplicate_email_is_conflict(client, registered):
    """Check 2: a second registration for the same address is 409, not 400 or 500."""
    response = client.post(
        "/api/v1/auth/register",
        json={"email": registered["email"], "password": PASSWORD},
    )
    assert response.status_code == 409


@pytest.mark.parametrize(
    "password",
    ["weak", "nouppercase1!", "NOLOWERCASE1!", "NoDigits!!", "NoSpecial123"],
)
def test_weak_passwords_rejected(client, password):
    """Check 3: each password rule is enforced, not just the length rule."""
    response = client.post(
        "/api/v1/auth/register", json={"email": _unique_email(), "password": password}
    )
    assert response.status_code == 422


def test_password_is_not_echoed_back(client, registered):
    """The registration response must never contain the submitted secret."""
    response = client.post(
        "/api/v1/auth/register",
        json={"email": _unique_email(), "password": PASSWORD},
    )
    assert PASSWORD not in response.text


# ----------------------------------------------------------------------- login


def test_login_succeeds(client, registered):
    """Correct credentials return a bearer token and a refresh token."""
    response = client.post(
        "/api/v1/auth/login",
        data={"email": registered["email"], "password": PASSWORD, "grant_type": "password"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["refresh_token"]
    assert body["email"] == registered["email"]
    assert body["username"] == "tester"


def test_wrong_password_is_unauthorized(client, registered):
    """Check 4: wrong password is 401."""
    response = client.post(
        "/api/v1/auth/login",
        data={"email": registered["email"], "password": "Wrong123!", "grant_type": "password"},
    )
    assert response.status_code == 401


def test_login_does_not_leak_account_existence(client, registered):
    """Unknown address and wrong password must be indistinguishable.

    Otherwise the endpoint is an oracle for which emails are registered.
    """
    unknown = client.post(
        "/api/v1/auth/login",
        data={"email": _unique_email(), "password": PASSWORD, "grant_type": "password"},
    )
    wrong = client.post(
        "/api/v1/auth/login",
        data={"email": registered["email"], "password": "Wrong123!", "grant_type": "password"},
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_unsupported_grant_type(client, registered):
    """Only the password grant is implemented."""
    response = client.post(
        "/api/v1/auth/login",
        data={
            "email": registered["email"],
            "password": PASSWORD,
            "grant_type": "client_credentials",
        },
    )
    assert response.status_code == 400


# ----------------------------------------------------------- token scope checks


def test_create_session_with_user_token(client, registered):
    """Check 5: a user token creates a session."""
    session_id, session_token = _new_session_token(client, registered["user_token"])
    assert session_id and session_token


def test_session_token_cannot_create_session(client, registered):
    """Check 6: a session token must not be accepted where a user token is required.

    This is the check that fails if the `typ` claim assertion is dropped.
    """
    _, session_token = _new_session_token(client, registered["user_token"])
    response = client.post("/api/v1/auth/session", headers=_auth(session_token))
    assert response.status_code == 401


def test_session_token_cannot_list_sessions(client, registered):
    """A leaked session token must not enumerate the user's other sessions."""
    _, session_token = _new_session_token(client, registered["user_token"])
    response = client.get("/api/v1/auth/sessions", headers=_auth(session_token))
    assert response.status_code == 401


def test_user_token_cannot_reach_session_endpoint(client, registered):
    """Check 7: the reverse direction — a user token is not a session token."""
    session_id, _ = _new_session_token(client, registered["user_token"])
    response = client.patch(
        f"/api/v1/auth/session/{session_id}/name",
        data={"name": "renamed"},
        headers=_auth(registered["user_token"]),
    )
    assert response.status_code == 401


# --------------------------------------------------------- malformed tokens


def test_tampered_signature_rejected(client, registered):
    """Check 8: mutating the token invalidates the signature."""
    response = client.get("/api/v1/auth/sessions", headers=_auth(registered["user_token"] + "x"))
    assert response.status_code == 401


def test_missing_credentials_rejected(client):
    """Check 9: HTTPBearer rejects a request with no Authorization header."""
    response = client.get("/api/v1/auth/sessions")
    assert response.status_code in (401, 403)


def test_garbage_token_rejected(client):
    """A non-JWT bearer value is a 401, not a 500."""
    response = client.get("/api/v1/auth/sessions", headers=_auth("not-a-jwt"))
    assert response.status_code == 401


# ------------------------------------------------------------ cross-user access


def test_cannot_rename_another_users_session(client, registered):
    """User B's session token must not rename user A's session."""
    a_session_id, _ = _new_session_token(client, registered["user_token"])

    other_email = _unique_email()
    other = client.post(
        "/api/v1/auth/register", json={"email": other_email, "password": PASSWORD}
    ).json()
    _, b_session_token = _new_session_token(client, other["token"]["access_token"])

    response = client.patch(
        f"/api/v1/auth/session/{a_session_id}/name",
        data={"name": "hijacked"},
        headers=_auth(b_session_token),
    )
    # 403: the token is valid and session-scoped, but scoped to a different session.
    assert response.status_code == 403


def test_sessions_list_is_scoped_to_owner(client, registered):
    """Listing returns only the caller's sessions."""
    _new_session_token(client, registered["user_token"])

    other = client.post(
        "/api/v1/auth/register", json={"email": _unique_email(), "password": PASSWORD}
    ).json()
    response = client.get("/api/v1/auth/sessions", headers=_auth(other["token"]["access_token"]))
    assert response.status_code == 200
    assert response.json() == []


# ------------------------------------------------------------------- refresh


def test_refresh_rotates_single_use(client, registered):
    """Check 10: the first refresh succeeds, replaying the same token fails."""
    first = client.post("/api/v1/auth/refresh", data={"refresh_token": registered["refresh_token"]})
    assert first.status_code == 200, first.text
    assert first.json()["refresh_token"] != registered["refresh_token"]

    replay = client.post(
        "/api/v1/auth/refresh", data={"refresh_token": registered["refresh_token"]}
    )
    assert replay.status_code == 401


def test_refreshed_token_works(client, registered):
    """The access token minted by a refresh is usable."""
    body = client.post(
        "/api/v1/auth/refresh", data={"refresh_token": registered["refresh_token"]}
    ).json()
    response = client.get("/api/v1/auth/sessions", headers=_auth(body["access_token"]))
    assert response.status_code == 200


def test_unknown_refresh_token_rejected(client):
    """An invented refresh token is 401."""
    response = client.post("/api/v1/auth/refresh", data={"refresh_token": "nope"})
    assert response.status_code == 401


# -------------------------------------------------------------------- logout


def test_logout_denylists_access_token(client, registered):
    """Check 11: after logout the presented access token stops working."""
    logout = client.post("/api/v1/auth/logout", headers=_auth(registered["user_token"]))
    assert logout.status_code == 204

    after = client.get("/api/v1/auth/sessions", headers=_auth(registered["user_token"]))
    assert after.status_code == 401


def test_logout_revokes_refresh_tokens(client, registered):
    """Logout also invalidates the refresh token, so it cannot mint a new session."""
    client.post("/api/v1/auth/logout", headers=_auth(registered["user_token"]))
    response = client.post(
        "/api/v1/auth/refresh", data={"refresh_token": registered["refresh_token"]}
    )
    assert response.status_code == 401


def test_logout_rejects_session_token(client, registered):
    """Logout is a user-scoped operation."""
    _, session_token = _new_session_token(client, registered["user_token"])
    response = client.post("/api/v1/auth/logout", headers=_auth(session_token))
    assert response.status_code == 401


# --------------------------------------------------------------- persistence


def test_password_is_bcrypt_hashed(registered):
    """The stored credential is a bcrypt hash, never the plaintext."""
    from sqlmodel import Session, select

    from app.models.user import User

    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == registered["email"])).first()
        assert user is not None
        assert user.hashed_password.startswith("$2b$")
        assert PASSWORD not in user.hashed_password


def test_refresh_tokens_stored_hashed(registered):
    """Only a SHA-256 digest of the refresh token is persisted."""
    from sqlmodel import Session, select

    from app.models.token import RefreshToken

    with Session(engine) as session:
        rows = list(session.exec(select(RefreshToken)).all())
        assert rows, "expected at least one stored refresh token"
        for row in rows:
            assert len(row.token_hash) == 64
            assert row.token_hash != registered["refresh_token"]


def test_session_tokens_are_not_interchangeable(client, registered):
    """Two sessions of the same user get tokens scoped to their own session."""
    first_id, first_token = _new_session_token(client, registered["user_token"])
    second_id, _ = _new_session_token(client, registered["user_token"])
    assert first_id != second_id

    response = client.patch(
        f"/api/v1/auth/session/{second_id}/name",
        data={"name": "wrong session"},
        headers=_auth(first_token),
    )
    assert response.status_code == 403


def test_delete_session(client, registered):
    """A session can be deleted with its own token and then no longer resolves."""
    session_id, session_token = _new_session_token(client, registered["user_token"])
    assert (
        client.delete(
            f"/api/v1/auth/session/{session_id}", headers=_auth(session_token)
        ).status_code
        == 204
    )
    # The token still verifies, but the row is gone.
    response = client.patch(
        f"/api/v1/auth/session/{session_id}/name",
        data={"name": "ghost"},
        headers=_auth(session_token),
    )
    assert response.status_code == 404
