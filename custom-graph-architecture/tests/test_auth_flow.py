"""End-to-end assertions for the authentication flow.

The executable form of the auth verification checklist: registration, login, refresh
rotation, logout revocation, and — the important ones — the two scope checks that make a
user token and a session token a real privilege boundary. A failure in
``test_session_token_cannot_create_session`` or
``test_user_token_cannot_reach_session_endpoint`` is a security regression, not a flaky
test.

Runs against the configured Postgres, so it is marked ``integration`` and skips when no
database is reachable:

    docker compose up -d db && uv run alembic upgrade head
    uv run pytest tests/test_auth_flow.py -v

Every account it creates uses the ``authtest-`` email prefix, and the module fixture
deletes those accounts (and everything hanging off them) on the way out — including any
left behind by an aborted earlier run. Direct database assertions go through plain
synchronous psycopg rather than the application engine, so the suite never shares an
async connection pool across two event loops.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from src.configs.config import settings
from src.main import app

pytestmark = pytest.mark.integration

PASSWORD = "Secret123!"  # noqa: S105 — test fixture value, not a credential
EMAIL_PREFIX = "authtest-"
API = settings.API_V1_STR


def _query(sql: str, params: tuple[Any, ...] | None = None) -> list[tuple[Any, ...]]:
    """Run one statement against the configured database and return any rows.

    ``params`` stays None when there is nothing to bind: psycopg only parses the string
    for placeholders when parameters are supplied, and a bare ``%`` in a LIKE pattern
    would otherwise be read as one.
    """
    with psycopg.connect(settings.psycopg_database_uri) as conn, conn.cursor() as cur:
        cur.execute(sql, params)  # type: ignore[arg-type]
        return cur.fetchall() if cur.description else []


@pytest.fixture(scope="module", autouse=True)
def _cleanup(require_postgres: None) -> Iterator[None]:
    """Delete every row this module creates, before and after it runs.

    Scoped by the ``authtest-`` email prefix and by start time rather than by table, so
    it can never truncate real data. Runs on entry as well as exit to clear anything an
    aborted run left behind.
    """
    started_at = datetime.now(UTC).replace(tzinfo=None)

    pattern = f"{EMAIL_PREFIX}%"
    owned = 'SELECT id FROM "user" WHERE email LIKE %s'

    def purge() -> None:
        _query(f"DELETE FROM refresh_token WHERE user_id IN ({owned})", (pattern,))
        _query(f'DELETE FROM "session" WHERE user_id IN ({owned})', (pattern,))
        _query('DELETE FROM "user" WHERE email LIKE %s', (pattern,))
        _query("DELETE FROM revoked_token WHERE created_at >= %s", (started_at,))

    purge()
    yield
    purge()


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    """TestClient with the app's lifespan run, so secret validation is exercised."""
    with TestClient(app) as test_client:
        yield test_client


def _unique_email() -> str:
    return f"{EMAIL_PREFIX}{uuid.uuid4().hex[:12]}@example.com"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def registered(client: TestClient) -> dict[str, Any]:
    """A freshly registered user plus their user token and refresh token."""
    email = _unique_email()
    response = client.post(
        f"{API}/auth/register",
        json={"email": email, "password": PASSWORD, "username": "tester"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return {
        "email": email,
        "id": body["id"],
        "user_token": body["token"]["access_token"],
        "refresh_token": body["refresh_token"],
    }


def _new_session_token(client: TestClient, user_token: str) -> tuple[str, str]:
    response = client.post(f"{API}/auth/session", headers=_auth(user_token))
    assert response.status_code == 201, response.text
    body = response.json()
    return body["session_id"], body["token"]["access_token"]


# ---------------------------------------------------------------- registration


def test_register_returns_tokens(registered: dict[str, Any]) -> None:
    """Registration yields both an access token and a refresh token."""
    assert registered["user_token"]
    assert registered["refresh_token"]


def test_duplicate_email_is_conflict(
    client: TestClient, registered: dict[str, Any]
) -> None:
    """A second registration for the same address is 409, not 400 or 500."""
    response = client.post(
        f"{API}/auth/register",
        json={"email": registered["email"], "password": PASSWORD},
    )
    assert response.status_code == 409


@pytest.mark.parametrize(
    "password",
    ["weak", "nouppercase1!", "NOLOWERCASE1!", "NoDigits!!", "NoSpecial123"],
)
def test_weak_passwords_rejected(client: TestClient, password: str) -> None:
    """Each password rule is enforced at the endpoint, not just the length rule."""
    response = client.post(
        f"{API}/auth/register",
        json={"email": _unique_email(), "password": password},
    )
    assert response.status_code == 422


def test_password_is_not_echoed_back(client: TestClient) -> None:
    """The registration response must never contain the submitted secret."""
    response = client.post(
        f"{API}/auth/register",
        json={"email": _unique_email(), "password": PASSWORD},
    )
    assert PASSWORD not in response.text


# ----------------------------------------------------------------------- login


def test_login_succeeds(client: TestClient, registered: dict[str, Any]) -> None:
    """Correct credentials return a bearer token and a refresh token."""
    response = client.post(
        f"{API}/auth/login",
        data={
            "email": registered["email"],
            "password": PASSWORD,
            "grant_type": "password",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["refresh_token"]
    assert body["email"] == registered["email"]
    assert body["username"] == "tester"


def test_wrong_password_is_unauthorized(
    client: TestClient, registered: dict[str, Any]
) -> None:
    """A wrong password is 401."""
    response = client.post(
        f"{API}/auth/login",
        data={
            "email": registered["email"],
            "password": "Wrong123!",
            "grant_type": "password",
        },
    )
    assert response.status_code == 401


def test_login_does_not_leak_account_existence(
    client: TestClient, registered: dict[str, Any]
) -> None:
    """Unknown address and wrong password must be indistinguishable.

    Otherwise the endpoint is an oracle for which emails are registered.
    """
    unknown = client.post(
        f"{API}/auth/login",
        data={
            "email": _unique_email(),
            "password": PASSWORD,
            "grant_type": "password",
        },
    )
    wrong = client.post(
        f"{API}/auth/login",
        data={
            "email": registered["email"],
            "password": "Wrong123!",
            "grant_type": "password",
        },
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_unsupported_grant_type(client: TestClient, registered: dict[str, Any]) -> None:
    """Only the password grant is implemented."""
    response = client.post(
        f"{API}/auth/login",
        data={
            "email": registered["email"],
            "password": PASSWORD,
            "grant_type": "client_credentials",
        },
    )
    assert response.status_code == 400


# ----------------------------------------------------------- token scope checks


def test_create_session_with_user_token(
    client: TestClient, registered: dict[str, Any]
) -> None:
    """A user token creates a session."""
    session_id, session_token = _new_session_token(client, registered["user_token"])
    assert session_id and session_token


def test_session_token_cannot_create_session(
    client: TestClient, registered: dict[str, Any]
) -> None:
    """A session token must not be accepted where a user token is required.

    This is the check that fails if the ``typ`` claim assertion is dropped.
    """
    _, session_token = _new_session_token(client, registered["user_token"])
    response = client.post(f"{API}/auth/session", headers=_auth(session_token))
    assert response.status_code == 401


def test_session_token_cannot_list_sessions(
    client: TestClient, registered: dict[str, Any]
) -> None:
    """A leaked session token must not enumerate the user's other sessions."""
    _, session_token = _new_session_token(client, registered["user_token"])
    response = client.get(f"{API}/auth/sessions", headers=_auth(session_token))
    assert response.status_code == 401


def test_user_token_cannot_reach_session_endpoint(
    client: TestClient, registered: dict[str, Any]
) -> None:
    """The reverse direction — a user token is not a session token."""
    session_id, _ = _new_session_token(client, registered["user_token"])
    response = client.patch(
        f"{API}/auth/session/{session_id}/name",
        data={"name": "renamed"},
        headers=_auth(registered["user_token"]),
    )
    assert response.status_code == 401


# ----------------------------------------------------------- malformed tokens


def test_tampered_signature_rejected(
    client: TestClient, registered: dict[str, Any]
) -> None:
    """Mutating the token invalidates the signature."""
    response = client.get(
        f"{API}/auth/sessions", headers=_auth(registered["user_token"] + "x")
    )
    assert response.status_code == 401


def test_missing_credentials_rejected(client: TestClient) -> None:
    """HTTPBearer rejects a request with no Authorization header."""
    response = client.get(f"{API}/auth/sessions")
    assert response.status_code in (401, 403)


def test_garbage_token_rejected(client: TestClient) -> None:
    """A non-JWT bearer value is a 401, not a 500."""
    response = client.get(f"{API}/auth/sessions", headers=_auth("not-a-jwt"))
    assert response.status_code == 401


# ------------------------------------------------------------ cross-user access


def test_cannot_rename_another_users_session(
    client: TestClient, registered: dict[str, Any]
) -> None:
    """User B's session token must not rename user A's session."""
    a_session_id, _ = _new_session_token(client, registered["user_token"])

    other = client.post(
        f"{API}/auth/register",
        json={"email": _unique_email(), "password": PASSWORD},
    ).json()
    _, b_session_token = _new_session_token(client, other["token"]["access_token"])

    response = client.patch(
        f"{API}/auth/session/{a_session_id}/name",
        data={"name": "hijacked"},
        headers=_auth(b_session_token),
    )
    # 403: the token is valid and session-scoped, but scoped to a different session.
    assert response.status_code == 403


def test_sessions_list_is_scoped_to_owner(
    client: TestClient, registered: dict[str, Any]
) -> None:
    """Listing returns only the caller's sessions."""
    _new_session_token(client, registered["user_token"])

    other = client.post(
        f"{API}/auth/register",
        json={"email": _unique_email(), "password": PASSWORD},
    ).json()
    response = client.get(
        f"{API}/auth/sessions", headers=_auth(other["token"]["access_token"])
    )
    assert response.status_code == 200
    assert response.json() == []


# ------------------------------------------------------------------- refresh


def test_refresh_rotates_single_use(
    client: TestClient, registered: dict[str, Any]
) -> None:
    """The first refresh succeeds; replaying the same token fails."""
    first = client.post(
        f"{API}/auth/refresh", data={"refresh_token": registered["refresh_token"]}
    )
    assert first.status_code == 200, first.text
    assert first.json()["refresh_token"] != registered["refresh_token"]

    replay = client.post(
        f"{API}/auth/refresh", data={"refresh_token": registered["refresh_token"]}
    )
    assert replay.status_code == 401


def test_refreshed_token_works(client: TestClient, registered: dict[str, Any]) -> None:
    """The access token minted by a refresh is usable."""
    body = client.post(
        f"{API}/auth/refresh", data={"refresh_token": registered["refresh_token"]}
    ).json()
    response = client.get(f"{API}/auth/sessions", headers=_auth(body["access_token"]))
    assert response.status_code == 200


def test_unknown_refresh_token_rejected(client: TestClient) -> None:
    """An invented refresh token is 401."""
    response = client.post(f"{API}/auth/refresh", data={"refresh_token": "nope"})
    assert response.status_code == 401


# -------------------------------------------------------------------- logout


def test_logout_denylists_access_token(
    client: TestClient, registered: dict[str, Any]
) -> None:
    """After logout the presented access token stops working."""
    logout = client.post(f"{API}/auth/logout", headers=_auth(registered["user_token"]))
    assert logout.status_code == 204

    after = client.get(f"{API}/auth/sessions", headers=_auth(registered["user_token"]))
    assert after.status_code == 401


def test_logout_revokes_refresh_tokens(
    client: TestClient, registered: dict[str, Any]
) -> None:
    """Logout also invalidates the refresh token, so it cannot mint a new session."""
    client.post(f"{API}/auth/logout", headers=_auth(registered["user_token"]))
    response = client.post(
        f"{API}/auth/refresh", data={"refresh_token": registered["refresh_token"]}
    )
    assert response.status_code == 401


def test_logout_rejects_session_token(
    client: TestClient, registered: dict[str, Any]
) -> None:
    """Logout is a user-scoped operation."""
    _, session_token = _new_session_token(client, registered["user_token"])
    response = client.post(f"{API}/auth/logout", headers=_auth(session_token))
    assert response.status_code == 401


# --------------------------------------------------------------- persistence


def test_password_is_bcrypt_hashed(registered: dict[str, Any]) -> None:
    """The stored credential is a bcrypt hash, never the plaintext."""
    rows = _query(
        'SELECT hashed_password FROM "user" WHERE email = %s', (registered["email"],)
    )
    assert rows, "expected the registered user to be persisted"
    stored = rows[0][0]
    assert stored.startswith("$2b$")
    assert PASSWORD not in stored


def test_refresh_tokens_stored_hashed(registered: dict[str, Any]) -> None:
    """Only a SHA-256 digest of the refresh token is persisted."""
    rows = _query(
        "SELECT token_hash FROM refresh_token WHERE user_id = %s", (registered["id"],)
    )
    assert rows, "expected at least one stored refresh token"
    for (token_hash,) in rows:
        assert len(token_hash) == 64
        assert token_hash != registered["refresh_token"]


# ------------------------------------------------------------------- sessions


def test_session_tokens_are_not_interchangeable(
    client: TestClient, registered: dict[str, Any]
) -> None:
    """Two sessions of the same user get tokens scoped to their own session."""
    first_id, first_token = _new_session_token(client, registered["user_token"])
    second_id, _ = _new_session_token(client, registered["user_token"])
    assert first_id != second_id

    response = client.patch(
        f"{API}/auth/session/{second_id}/name",
        data={"name": "wrong session"},
        headers=_auth(first_token),
    )
    assert response.status_code == 403


def test_rename_session(client: TestClient, registered: dict[str, Any]) -> None:
    """A session can be renamed with its own token."""
    session_id, session_token = _new_session_token(client, registered["user_token"])
    response = client.patch(
        f"{API}/auth/session/{session_id}/name",
        data={"name": "leg day"},
        headers=_auth(session_token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "leg day"


def test_delete_session(client: TestClient, registered: dict[str, Any]) -> None:
    """A session can be deleted with its own token and then no longer resolves."""
    session_id, session_token = _new_session_token(client, registered["user_token"])
    deleted = client.delete(
        f"{API}/auth/session/{session_id}", headers=_auth(session_token)
    )
    assert deleted.status_code == 204

    # The token still verifies, but the row is gone.
    response = client.patch(
        f"{API}/auth/session/{session_id}/name",
        data={"name": "ghost"},
        headers=_auth(session_token),
    )
    assert response.status_code == 404
