"""Persistence for users, sessions, refresh tokens, and the revocation denylist.

Every method here opens a short synchronous SQLAlchemy session against the
engine in ``app.models.database``. See the note in the module-level docstring of
``app.api.v1.auth`` about the async trade-off this implies.
"""

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlmodel import Session, col, select

from app.core.logging import logger
from app.models.database import engine
from app.models.session import Session as ChatSession
from app.models.token import RefreshToken, RevokedToken
from app.models.user import User


class DatabaseService:
    """Data access for the authentication layer."""

    def __init__(self) -> None:
        self.engine = engine

    # ---------------------------------------------------------------- users

    async def create_user(self, email: str, password: str, username: str | None = None) -> User:
        """Create a user.

        Args:
            email: Sanitized, lowercased email address.
            password: Already-hashed password. Never a plaintext value.
            username: Optional display name.
        """
        with Session(self.engine) as session:
            user = User(email=email, hashed_password=password, username=username)
            session.add(user)
            session.commit()
            session.refresh(user)
            logger.info("user_created", user_id=user.id)
            return user

    async def get_user(self, user_id: int) -> User | None:
        """Fetch a user by id."""
        with Session(self.engine) as session:
            return session.get(User, user_id)

    async def get_user_by_email(self, email: str) -> User | None:
        """Fetch a user by email."""
        with Session(self.engine) as session:
            return session.exec(select(User).where(User.email == email)).first()

    async def delete_user_by_email(self, email: str) -> bool:
        """Delete a user. Returns False when no such user exists."""
        with Session(self.engine) as session:
            user = session.exec(select(User).where(User.email == email)).first()
            if user is None:
                return False
            session.delete(user)
            session.commit()
            logger.info("user_deleted", user_id=user.id)
            return True

    # ------------------------------------------------------------- sessions

    async def create_session(
        self, session_id: str, user_id: int, name: str = "", username: str | None = None
    ) -> ChatSession:
        """Create a session owned by ``user_id``."""
        with Session(self.engine) as session:
            chat_session = ChatSession(id=session_id, user_id=user_id, name=name, username=username)
            session.add(chat_session)
            session.commit()
            session.refresh(chat_session)
            logger.info("session_created", session_id=session_id, user_id=user_id)
            return chat_session

    async def get_session(self, session_id: str) -> ChatSession | None:
        """Fetch a session by id."""
        with Session(self.engine) as session:
            return session.get(ChatSession, session_id)

    async def get_user_sessions(self, user_id: int) -> list[ChatSession]:
        """List a user's sessions, oldest first."""
        with Session(self.engine) as session:
            statement = (
                select(ChatSession)
                .where(col(ChatSession.user_id) == user_id)
                .order_by(col(ChatSession.created_at))
            )
            return list(session.exec(statement).all())

    async def update_session_name(self, session_id: str, name: str) -> ChatSession:
        """Rename a session.

        Raises:
            HTTPException: 404 if the session does not exist.
        """
        with Session(self.engine) as session:
            chat_session = session.get(ChatSession, session_id)
            if chat_session is None:
                raise HTTPException(status_code=404, detail="Session not found")
            chat_session.name = name
            session.add(chat_session)
            session.commit()
            session.refresh(chat_session)
            logger.info("session_name_updated", session_id=session_id)
            return chat_session

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session. Returns False when no such session exists."""
        with Session(self.engine) as session:
            chat_session = session.get(ChatSession, session_id)
            if chat_session is None:
                return False
            session.delete(chat_session)
            session.commit()
            logger.info("session_deleted", session_id=session_id)
            return True

    # -------------------------------------------------------- refresh tokens

    async def store_refresh_token(
        self, user_id: int, token_hash: str, expires_at: datetime
    ) -> None:
        """Persist a hashed refresh token."""
        with Session(self.engine) as session:
            session.add(RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at))
            session.commit()

    async def consume_refresh_token(self, token_hash: str) -> int | None:
        """Validate and revoke a refresh token, returning its owner's id.

        Refresh tokens are single-use: presenting one both consumes it and mints
        a replacement, so a stolen token is only good until the legitimate client
        next refreshes.

        Returns:
            Optional[int]: The user id, or None if the token is unknown, already
            consumed, revoked, or expired.
        """
        with Session(self.engine) as session:
            record = session.exec(
                select(RefreshToken).where(RefreshToken.token_hash == token_hash)
            ).first()
            if record is None or record.revoked_at is not None:
                return None

            expires_at = record.expires_at
            # SQLite (and Postgres columns declared without a timezone) hand back
            # naive datetimes; compare in UTC rather than crashing on the mismatch.
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= datetime.now(UTC):
                return None

            record.revoked_at = datetime.now(UTC)
            session.add(record)
            session.commit()
            return record.user_id

    async def revoke_user_refresh_tokens(self, user_id: int) -> int:
        """Revoke every live refresh token for a user.

        Returns:
            int: How many tokens were revoked.
        """
        with Session(self.engine) as session:
            records = list(
                session.exec(
                    select(RefreshToken).where(
                        col(RefreshToken.user_id) == user_id,
                        col(RefreshToken.revoked_at).is_(None),
                    )
                ).all()
            )
            now = datetime.now(UTC)
            for record in records:
                record.revoked_at = now
                session.add(record)
            session.commit()
            return len(records)

    # ------------------------------------------------------------- denylist

    async def revoke_jti(self, jti: str, expires_at: datetime) -> None:
        """Denylist an access-token jti until its natural expiry."""
        with Session(self.engine) as session:
            if session.get(RevokedToken, jti) is None:
                session.add(RevokedToken(jti=jti, expires_at=expires_at))
                session.commit()

    async def is_jti_revoked(self, jti: str) -> bool:
        """Check the denylist."""
        with Session(self.engine) as session:
            return session.get(RevokedToken, jti) is not None

    async def purge_expired_tokens(self) -> int:
        """Delete denylist and refresh rows past their expiry.

        Nothing calls this yet. Both tables grow without bound until it is wired
        to a periodic task or an external cron.

        Returns:
            int: How many rows were deleted.
        """
        with Session(self.engine) as session:
            now = datetime.now(UTC)
            stale_jtis = list(
                session.exec(select(RevokedToken).where(col(RevokedToken.expires_at) <= now)).all()
            )
            stale_refresh = list(
                session.exec(select(RefreshToken).where(col(RefreshToken.expires_at) <= now)).all()
            )
            for row in (*stale_jtis, *stale_refresh):
                session.delete(row)
            session.commit()
            deleted = len(stale_jtis) + len(stale_refresh)
            if deleted:
                logger.info("expired_tokens_purged", count=deleted)
            return deleted

    # ----------------------------------------------------------------- misc

    async def health_check(self) -> bool:
        """Return True when the database answers a trivial query."""
        try:
            with Session(self.engine) as session:
                session.exec(select(1))
            return True
        except Exception as exc:
            logger.error("database_health_check_failed", error=str(exc))
            return False


database_service = DatabaseService()
