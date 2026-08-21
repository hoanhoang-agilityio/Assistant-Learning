"""User model."""

from typing import TYPE_CHECKING

import bcrypt
from sqlmodel import Field, Relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.session import Session

# bcrypt hashes at most 72 bytes and silently ignores the rest. Without an
# explicit guard, a 100-character password and its 72-byte prefix would both
# authenticate, so the extra length would be security theatre.
_MAX_BCRYPT_BYTES = 72


class User(BaseModel, table=True):
    """User account."""

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    username: str | None = Field(default=None, index=False)
    sessions: list["Session"] = Relationship(back_populates="user")

    def verify_password(self, password: str) -> bool:
        """Verify a plaintext password against the stored hash.

        Returns False rather than raising on a malformed stored hash, so a
        corrupted row is an authentication failure and not a 500.
        """
        try:
            return bcrypt.checkpw(password.encode("utf-8"), self.hashed_password.encode("utf-8"))
        except ValueError:
            return False

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password with a fresh bcrypt salt.

        Raises:
            ValueError: If the password exceeds what bcrypt can actually hash.
        """
        encoded = password.encode("utf-8")
        if len(encoded) > _MAX_BCRYPT_BYTES:
            raise ValueError(
                f"Password must not exceed {_MAX_BCRYPT_BYTES} bytes when UTF-8 encoded"
            )
        return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


from app.models.session import Session  # noqa: E402
