"""The sign-in gate.

Nothing else in the UI renders until this returns a signed-in user, because
every other endpoint is behind a token: there is no anonymous mode to fall back
to. Registration and sign-in are two tabs rather than two pages, so a failed
sign-in does not lose the email that was already typed.

The password rules are imported from ``app.utils.sanitization`` rather than
restated, so the hint under the field cannot drift from what the API enforces.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import streamlit as st

from app.ui import api_client, state
from app.ui.wording import TAGLINE
from app.utils.sanitization import MIN_PASSWORD_LENGTH

_PASSWORD_HELP = (
    f"At least {MIN_PASSWORD_LENGTH} characters, with an uppercase letter, a lowercase "
    "letter, a number and a special character."
)


def _error_text(exc: httpx.HTTPError) -> str:
    """Turn an auth failure into one sentence the user can act on.

    The validation handler in ``app/main.py`` returns per-field messages under
    ``errors`` and a generic ``detail``; showing only the latter would tell a
    user with a weak password nothing more than "Validation error".

    Args:
        exc: The failure.

    Returns:
        The message to show.
    """
    if not isinstance(exc, httpx.HTTPStatusError):
        return f"Couldn't reach the server: {exc}"

    try:
        body: Any = exc.response.json()
    except (json.JSONDecodeError, ValueError):
        return f"The server returned {exc.response.status_code}."

    errors = body.get("errors") if isinstance(body, dict) else None
    if isinstance(errors, list) and errors:
        return " ".join(str(item.get("message", "")).strip() for item in errors).strip()

    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, str):
        return detail
    return f"The server returned {exc.response.status_code}."


def _after_credentials(client: httpx.Client) -> None:
    """Load the user's conversations, then redraw as the signed-in app.

    Args:
        client: An open API client.
    """
    try:
        state.sync_conversations(client)
    except httpx.HTTPError:
        # Signed in, but the conversation list did not load. The sidebar renders
        # empty and its own refresh path reports the problem — better than
        # bouncing the user back to a sign-in form that would succeed again.
        pass
    st.rerun()


def _render_sign_in(client: httpx.Client) -> None:
    """Render the sign-in form and handle its submission.

    Args:
        client: An open API client.
    """
    with st.form("sign_in", border=False):
        email = st.text_input("Email", key="sign_in_email", autocomplete="username")
        password = st.text_input(
            "Password", type="password", key="sign_in_password", autocomplete="current-password"
        )
        submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)

    if not submitted:
        return
    if not email or not password:
        st.session_state.auth_error = "Enter your email and password."
        st.rerun()

    try:
        tokens = api_client.login(client, email=email, password=password)
    except httpx.HTTPError as exc:
        st.session_state.auth_error = _error_text(exc)
        st.rerun()
        return

    state.sign_in(
        email=tokens.get("email") or email,
        username=tokens.get("username"),
        access_token=tokens["access_token"],
        expires_at=tokens["expires_at"],
        refresh_token=tokens["refresh_token"],
    )
    _after_credentials(client)


def _render_register(client: httpx.Client) -> None:
    """Render the registration form and handle its submission.

    Args:
        client: An open API client.
    """
    with st.form("register", border=False):
        email = st.text_input("Email", key="register_email", autocomplete="username")
        username = st.text_input("Display name (optional)", key="register_username")
        password = st.text_input(
            "Password",
            type="password",
            key="register_password",
            help=_PASSWORD_HELP,
            autocomplete="new-password",
        )
        confirm = st.text_input(
            "Confirm password",
            type="password",
            key="register_confirm",
            autocomplete="new-password",
        )
        submitted = st.form_submit_button(
            "Create account", type="primary", use_container_width=True
        )

    if not submitted:
        return
    if not email or not password:
        st.session_state.auth_error = "Enter an email and a password."
        st.rerun()
    # Checked here as well as server-side: a mismatch is the one registration
    # error the API cannot detect, since it only ever sees one of the two.
    if password != confirm:
        st.session_state.auth_error = "Those passwords don't match."
        st.rerun()

    try:
        account = api_client.register(
            client, email=email, password=password, username=username or None
        )
    except httpx.HTTPError as exc:
        st.session_state.auth_error = _error_text(exc)
        st.rerun()
        return

    state.sign_in(
        email=account["email"],
        username=account.get("username"),
        access_token=account["token"]["access_token"],
        expires_at=account["token"]["expires_at"],
        refresh_token=account["refresh_token"],
    )
    _after_credentials(client)


def render_auth_gate(client: httpx.Client) -> None:
    """Draw the sign-in screen.

    Args:
        client: An open API client.
    """
    st.markdown(
        '<div class="pt-welcome">'
        '<p class="pt-welcome__title">🏋️ PT AI</p>'
        f'<p class="pt-empty-state">{TAGLINE} — sign in to pick up your '
        "conversations and your saved plans.</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    error = st.session_state.auth_error
    if error:
        st.markdown(f'<div class="pt-form-error">⚠ {error}</div>', unsafe_allow_html=True)

    sign_in_tab, register_tab = st.tabs(["Sign in", "Create account"])
    with sign_in_tab:
        _render_sign_in(client)
    with register_tab:
        _render_register(client)


__all__ = ["render_auth_gate"]
