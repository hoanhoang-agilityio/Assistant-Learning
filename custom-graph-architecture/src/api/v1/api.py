"""Aggregates the version 1 routers."""

from fastapi import APIRouter

from src.api.v1.auth import router as auth_router
from src.api.v1.chat import router as chat_router
from src.api.v1.health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["Health"])
api_router.include_router(auth_router, prefix="/auth", tags=["Auth"])
api_router.include_router(chat_router, tags=["Chat"])
