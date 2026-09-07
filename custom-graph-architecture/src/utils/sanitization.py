"""Input sanitization and password-strength rules.

Scope note: these helpers are for values that get echoed back to a client or rendered
downstream. They are deliberately **not** applied to passwords (which would change what
gets hashed) or to bearer tokens (which would corrupt the signature check).
"""

import html
import re

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
_SCRIPT_RE = re.compile(
    r"&lt;script.*?&gt;.*?&lt;/script&gt;", re.DOTALL | re.IGNORECASE
)

MIN_PASSWORD_LENGTH = 8


def sanitize_string(value: str) -> str:
    """HTML-escape a string and strip null bytes."""
    if not isinstance(value, str):
        value = str(value)
    value = html.escape(value)
    value = _SCRIPT_RE.sub("", value)
    return value.replace("\0", "")


def sanitize_email(email: str) -> str:
    """Sanitize, validate, and lowercase an email address.

    Raises:
        ValueError: If the address does not look like an email.
    """
    email = sanitize_string(email)
    if not _EMAIL_RE.match(email):
        raise ValueError("Invalid email format")
    return email.lower()


def validate_password_strength(password: str) -> bool:
    """Validate password strength.

    Single source of truth for the rules — the Pydantic validator on ``UserCreate``
    calls this rather than restating the regexes, so the two cannot drift apart.

    Returns:
        bool: True when the password passes every rule.

    Raises:
        ValueError: With the specific rule that failed.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long"
        )
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter")
    if not re.search(r"[0-9]", password):
        raise ValueError("Password must contain at least one number")
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        raise ValueError("Password must contain at least one special character")
    return True
