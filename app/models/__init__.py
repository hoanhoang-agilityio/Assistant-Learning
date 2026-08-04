"""SQLModel table definitions.

Every table model must be imported here. Alembic's autogenerate reads
``SQLModel.metadata``, which is only populated as a side effect of importing the
modules that define the tables — a model that is never imported produces a
silently empty migration.
"""

from app.models.base import BaseModel
from app.models.session import Session
from app.models.token import RefreshToken, RevokedToken
from app.models.user import User

__all__ = ["BaseModel", "RefreshToken", "RevokedToken", "Session", "User"]
