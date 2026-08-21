"""Persistence for users, sessions, refresh tokens, and the revocation denylist.

Every method opens a short-lived ``AsyncSession`` from the application session factory in
``src/services/database.py``. Unlike the sync-inside-async pattern this layer was ported
from, the calls here really are non-blocking, so an authenticated request does not stall
the event loop while it checks the denylist.
"""

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlmodel import col, select

from src.models.session import Session as ChatSession
from src.models.token import RefreshToken, RevokedToken
from src.models.user import User
from src.services.database import session_factory
from src.utils.logging import logger


class AuthService:
    """Data access for the authentication layer."""

    # ---------------------------------------------------------------- users

    async def create_user(
        self, email: str, password: str, username: str | None = None
    ) -> User:
        """Create a user.

        Args:
            email: Sanitized, lowercased email address.
            password: Already-hashed password. Never a plaintext value.
            username: Optional display name.

        Returns:
            User: The persisted row, with its assigned id.
        """
        async with session_factory() as session:
            user = User(email=email, hashed_password=password, username=username)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info("user_created", user_id=user.id)
            return user

    async def get_user(self, user_id: int) -> User | None:
        """Fetch a user by id."""
        async with session_factory() as session:
            return await session.get(User, user_id)

    async def get_user_by_email(self, email: str) -> User | None:
        """Fetch a user by email."""
        async with session_factory() as session:
            result = await session.execute(select(User).where(User.email == email))
            return result.scalars().first()

    async def delete_user_by_email(self, email: str) -> bool:
        """Delete a user and everything hanging off them.

        Sessions and refresh tokens carry a foreign key to ``user.id`` with no database
        cascade, so they are removed first — otherwise the delete fails on the
        constraint rather than doing what it says.

        Returns:
            bool: False when no such user exists.
        """
        async with session_factory() as session:
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalars().first()
            if user is None:
                return False

            for model in (ChatSession, RefreshToken):
                rows = await session.execute(
                    select(model).where(col(model.user_id) == user.id)
                )
                for row in rows.scalars().all():
                    await session.delete(row)

            await session.delete(user)
            await session.commit()
            logger.info("user_deleted", user_id=user.id)
            return True

    # ------------------------------------------------------------- sessions

    async def create_session(
        self,
        session_id: str,
        user_id: int,
        name: str = "",
        username: str | None = None,
    ) -> ChatSession:
        """Create a session owned by ``user_id``."""
        async with session_factory() as session:
            chat_session = ChatSession(
                id=session_id, user_id=user_id, name=name, username=username
            )
            session.add(chat_session)
            await session.commit()
            await session.refresh(chat_session)
            logger.info("session_created", session_id=session_id, user_id=user_id)
            return chat_session

    async def get_session(self, session_id: str) -> ChatSession | None:
        """Fetch a session by id."""
        async with session_factory() as session:
            return await session.get(ChatSession, session_id)

    async def get_user_sessions(self, user_id: int) -> list[ChatSession]:
        """List a user's sessions, oldest first."""
        async with session_factory() as session:
            result = await session.execute(
                select(ChatSession)
                .where(col(ChatSession.user_id) == user_id)
                .order_by(col(ChatSession.created_at))
            )
            return list(result.scalars().all())

    async def update_session_name(self, session_id: str, name: str) -> ChatSession:
        """Rename a session.

        Raises:
            HTTPException: 404 if the session does not exist.
        """
        async with session_factory() as session:
            chat_session = await session.get(ChatSession, session_id)
            if chat_session is None:
                raise HTTPException(status_code=404, detail="Session not found")
            chat_session.name = name
            session.add(chat_session)
            await session.commit()
            await session.refresh(chat_session)
            logger.info("session_name_updated", session_id=session_id)
            return chat_session

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session. Returns False when no such session exists."""
        async with session_factory() as session:
            chat_session = await session.get(ChatSession, session_id)
            if chat_session is None:
                return False
            await session.delete(chat_session)
            await session.commit()
            logger.info("session_deleted", session_id=session_id)
            return True

    # -------------------------------------------------------- refresh tokens

    async def store_refresh_token(
        self, user_id: int, token_hash: str, expires_at: datetime
    ) -> None:
        """Persist a hashed refresh token."""
        async with session_factory() as session:
            session.add(
                RefreshToken(
                    user_id=user_id, token_hash=token_hash, expires_at=expires_at
                )
            )
            await session.commit()

    async def consume_refresh_token(self, token_hash: str) -> int | None:
        """Validate and revoke a refresh token, returning its owner's id.

        Refresh tokens are single-use: presenting one both consumes it and mints a
        replacement, so a stolen token is only good until the legitimate client next
        refreshes.

        Returns:
            int | None: The user id, or None if the token is unknown, already consumed,
            revoked, or expired.
        """
        async with session_factory() as session:
            result = await session.execute(
                select(RefreshToken).where(RefreshToken.token_hash == token_hash)
            )
            record = result.scalars().first()
            if record is None or record.revoked_at is not None:
                return None

            expires_at = record.expires_at
            # Postgres columns declared without a timezone hand back naive datetimes;
            # compare in UTC rather than crashing on the mismatch.
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= datetime.now(UTC):
                return None

            record.revoked_at = datetime.now(UTC)
            session.add(record)
            await session.commit()
            return record.user_id

    async def revoke_user_refresh_tokens(self, user_id: int) -> int:
        """Revoke every live refresh token for a user.

        Returns:
            int: How many tokens were revoked.
        """
        async with session_factory() as session:
            result = await session.execute(
                select(RefreshToken).where(
                    col(RefreshToken.user_id) == user_id,
                    col(RefreshToken.revoked_at).is_(None),
                )
            )
            records = list(result.scalars().all())
            now = datetime.now(UTC)
            for record in records:
                record.revoked_at = now
                session.add(record)
            await session.commit()
            return len(records)

    # ------------------------------------------------------------- denylist

    async def revoke_jti(self, jti: str, expires_at: datetime) -> None:
        """Denylist an access-token jti until its natural expiry."""
        async with session_factory() as session:
            if await session.get(RevokedToken, jti) is None:
                session.add(RevokedToken(jti=jti, expires_at=expires_at))
                await session.commit()

    async def is_jti_revoked(self, jti: str) -> bool:
        """Check the denylist."""
        async with session_factory() as session:
            return await session.get(RevokedToken, jti) is not None

    async def purge_expired_tokens(self) -> int:
        """Delete denylist and refresh rows past their expiry.

        Nothing calls this yet. Both tables grow without bound until it is wired to a
        periodic task or an external cron.

        Returns:
            int: How many rows were deleted.
        """
        async with session_factory() as session:
            now = datetime.now(UTC)
            deleted = 0
            for model in (RevokedToken, RefreshToken):
                rows = await session.execute(
                    select(model).where(col(model.expires_at) <= now)
                )
                for row in rows.scalars().all():
                    await session.delete(row)
                    deleted += 1
            await session.commit()
            if deleted:
                logger.info("expired_tokens_purged", count=deleted)
            return deleted


auth_service = AuthService()
