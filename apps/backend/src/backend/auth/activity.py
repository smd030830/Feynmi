"""Idle expiration keyed by the sign-in time carried in the verified token."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import LoginSession
from backend.errors import AppError

IDLE_TIMEOUT = timedelta(hours=3)


async def enforce_idle_timeout(
    db: AsyncSession, user_id: UUID, auth_time: datetime, *, touch: bool = True
) -> None:
    now = datetime.now(UTC)
    cutoff = now - IDLE_TIMEOUT
    if not touch:
        session = await db.get(LoginSession, (user_id, auth_time))
        last_activity = session.last_activity_at if session else auth_time
    else:
        # An old sign-in without activity cannot be revived by a refreshed ID token.
        statement = insert(LoginSession).values(
            user_id=user_id,
            auth_time=auth_time,
            last_activity_at=now if auth_time > cutoff else auth_time,
        )
        last_activity = await db.scalar(
            statement.on_conflict_do_update(
                index_elements=[LoginSession.user_id, LoginSession.auth_time],
                set_={"last_activity_at": func.greatest(LoginSession.last_activity_at, now)},
                where=LoginSession.last_activity_at > cutoff,
            ).returning(LoginSession.last_activity_at)
        )
    if last_activity is None or last_activity <= cutoff:
        raise AppError(401, "session_idle_timeout", "login session expired due to inactivity")
    if touch:
        await db.commit()
