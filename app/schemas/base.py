"""Shared response base."""

from pydantic import BaseModel, ConfigDict


class BaseResponse(BaseModel):
    """Base class for API response models.

    ``from_attributes`` lets a response be built straight from an ORM row.
    """

    model_config = ConfigDict(from_attributes=True)
