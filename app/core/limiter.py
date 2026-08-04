"""Request rate limiting.

Keyed on the client IP, which is what protects register/login/refresh from
credential stuffing before any user identity exists. When VALKEY_HOST is set the
counters live in Valkey so limits hold across replicas; otherwise they are
per-process and a multi-replica deployment effectively multiplies every limit by
the replica count.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.configs.config import settings
from app.core.logging import logger

_storage_uri: str | None = None
if settings.VALKEY_HOST:
    _password_part = f":{settings.VALKEY_PASSWORD}@" if settings.VALKEY_PASSWORD else ""
    _storage_uri = (
        f"redis://{_password_part}{settings.VALKEY_HOST}"
        f":{settings.VALKEY_PORT}/{settings.VALKEY_DB}"
    )
    logger.info("rate_limiter_using_valkey", host=settings.VALKEY_HOST, port=settings.VALKEY_PORT)
else:
    logger.warning("rate_limiter_in_memory", detail="limits are per-process, not shared")

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=settings.RATE_LIMIT_DEFAULT,
    storage_uri=_storage_uri,
)
