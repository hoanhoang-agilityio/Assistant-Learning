"""SQLModel ORM models. Alembic owns their migrations.

Every table model must be imported here. ``alembic revision --autogenerate`` reads
``SQLModel.metadata``, which is only populated as a side effect of importing the modules
that define the tables — a model that is never imported produces a silently empty
migration.
"""

from src.models.base import BaseModel
from src.models.session import Session
from src.models.token import RefreshToken, RevokedToken
from src.models.user import User

__all__ = [
    "BaseModel",
    "RefreshToken",
    "RevokedToken",
    "Session",
    "User",
]
