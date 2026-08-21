"""Input sanitization and password-strength rules.

Scope note: these helpers are for values that get echoed back to a client or
rendered downstream. They are deliberately **not** applied to passwords (which
would change what gets hashed) or to bearer tokens (which would corrupt the
signature check).

``sanitize_prompt_text`` is the one helper here whose downstream is a *prompt*
rather than a browser, so it does not HTML-escape: `&amp;` in a system message
is noise a model has to read past.
"""

import html
import re
from typing import Any

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
_SCRIPT_RE = re.compile(r"&lt;script.*?&gt;.*?&lt;/script&gt;", re.DOTALL | re.IGNORECASE)

# What a line of free text would need to open a section of its own once it is
# interpolated into a prompt: markdown structure, fences, and pseudo-tags. They
# are removed rather than escaped, because a model reads an escaped `#` as a
# heading anyway, and nothing that consumes these fields needs them.
_PROMPT_MARKUP_RE = re.compile(r"[`#*_>\[\]{}<>|]")

MIN_PASSWORD_LENGTH = 8


def sanitize_string(value: str) -> str:
    """HTML-escape a string and strip null bytes."""
    if not isinstance(value, str):
        value = str(value)
    value = html.escape(value)
    value = _SCRIPT_RE.sub("", value)
    return value.replace("\0", "")


def sanitize_prompt_text(value: object, max_chars: int) -> str:
    """Flatten text bound for a prompt into one bounded, marker-free line.

    Model-written free text that is stored and then interpolated into a later
    prompt is the one place a value can become an instruction: the supervisor
    renders the user's profile into its **system** message, so a stored
    preference containing a newline and a `#` opens a heading of its own there,
    on every turn from then on.

    Applied at both ends of those fields on purpose — where the extractor's
    output is cleaned, and again where it is rendered. The second call is what
    covers rows written before the first one existed, and callers other than the
    extractor.

    Args:
        value: The text to flatten. Coerced to ``str``.
        max_chars: Hard bound on the result, in characters.

    Returns:
        The text as a single line with no markup, at most ``max_chars`` long.
        Empty when nothing survives — callers should treat that as "not stated"
        rather than storing it.
    """
    stripped = _PROMPT_MARKUP_RE.sub("", str(value).replace("\0", ""))
    return " ".join(stripped.split())[:max_chars].rstrip()


def sanitize_email(email: str) -> str:
    """Sanitize, validate, and lowercase an email address.

    Raises:
        ValueError: If the address does not look like an email.
    """
    email = sanitize_string(email)
    if not _EMAIL_RE.match(email):
        raise ValueError("Invalid email format")
    return email.lower()


def sanitize_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively sanitize every string value in a dictionary."""
    return {
        key: (
            sanitize_string(value)
            if isinstance(value, str)
            else sanitize_dict(value)
            if isinstance(value, dict)
            else sanitize_list(value)
            if isinstance(value, list)
            else value
        )
        for key, value in data.items()
    }


def sanitize_list(data: list[Any]) -> list[Any]:
    """Recursively sanitize every string value in a list."""
    return [
        sanitize_string(item)
        if isinstance(item, str)
        else sanitize_dict(item)
        if isinstance(item, dict)
        else sanitize_list(item)
        if isinstance(item, list)
        else item
        for item in data
    ]


def validate_password_strength(password: str) -> bool:
    """Validate password strength.

    Single source of truth for the rules — the Pydantic validator on
    ``UserCreate`` calls this rather than restating the regexes, so the two
    cannot drift apart.

    Returns:
        bool: True when the password passes every rule.

    Raises:
        ValueError: With the specific rule that failed.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter")
    if not re.search(r"[0-9]", password):
        raise ValueError("Password must contain at least one number")
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        raise ValueError("Password must contain at least one special character")
    return True
