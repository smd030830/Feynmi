"""Account settings and resumable deletion; no real cloud calls in tests."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.db.models import User, UserSettings
from backend.domain.enums import UserStatus
from backend.errors import AppError
from backend.services.cloud import AVATAR_LIMIT, AccountCloud

logger = logging.getLogger(__name__)


async def lock_identity(db: AsyncSession, uid: str) -> None:
    # Shared by first provisioning and deletion, including separate processes.
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:uid, 0))"), {"uid": uid})


async def active_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await db.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user is None or user.status != UserStatus.ACTIVE:
        raise AppError(409, "account_deleting", "account deletion is in progress")
    return user


async def settings(db: AsyncSession, user_id: uuid.UUID) -> UserSettings:
    await db.execute(insert(UserSettings).values(user_id=user_id).on_conflict_do_nothing())
    row = await db.get(UserSettings, user_id)
    assert row is not None
    return row


def summarize_agent(value: str) -> str:
    browser = "기타 브라우저"
    for marker, label in (
        ("Edg/", "Edge"),
        ("OPR/", "Opera"),
        ("Chrome/", "Chrome"),
        ("Firefox/", "Firefox"),
        ("Safari/", "Safari"),
    ):
        if marker in value:
            browser = label
            break
    system = "기타 OS"
    for marker, label in (
        ("Android", "Android"),
        ("iPhone", "iOS"),
        ("iPad", "iPadOS"),
        ("Windows", "Windows"),
        ("Macintosh", "macOS"),
        ("Linux", "Linux"),
    ):
        if marker in value:
            system = label
            break
    return f"{browser} · {system}"


def avatar_path(user_id: uuid.UUID, content_type: str) -> str:
    extension = {"image/jpeg": "jpg", "image/png": "png"}.get(content_type)
    if extension is None:
        raise AppError(400, "validation_error", "only JPG and PNG are supported")
    return f"users/{user_id}/avatar/{uuid.uuid4()}.{extension}"


def validate_avatar(content_type: str, data: bytes) -> None:
    if not data or len(data) > AVATAR_LIMIT:
        raise AppError(400, "validation_error", "invalid avatar size")
    png = content_type == "image/png" and data.startswith(b"\x89PNG\r\n\x1a\n")
    jpg = content_type == "image/jpeg" and data.startswith(b"\xff\xd8\xff")
    if not (png or jpg):
        raise AppError(400, "validation_error", "avatar format does not match its content")


async def _replace_avatar(
    factory: async_sessionmaker[AsyncSession],
    cloud: AccountCloud,
    user_id: uuid.UUID,
    content_type: str,
    data: bytes,
) -> str:
    """Keep the user row locked until all cloud writes and the DB commit settle."""
    async with factory() as db:
        user = await active_user(db, user_id)
        path = avatar_path(user_id, content_type)
        previous = user.avatar_path
        try:
            await asyncio.to_thread(cloud.upload_avatar, path, content_type, data)
            url = await asyncio.to_thread(cloud.read_url, path)
            user.avatar_path = path
            await db.commit()
        except Exception:
            # Upload may have succeeded before a transport error was reported.
            try:
                await asyncio.to_thread(cloud.delete_file, path)
            finally:
                await db.rollback()
            raise
        if previous:
            try:
                await asyncio.to_thread(cloud.delete_file, previous)
            except Exception:
                # The new pointer has committed; never roll it back to a deleted object.
                logger.warning("Previous avatar cleanup failed")
        return url


async def replace_avatar(
    factory: async_sessionmaker[AsyncSession],
    cloud: AccountCloud,
    user_id: uuid.UUID,
    content_type: str,
    data: bytes,
) -> str:
    validate_avatar(content_type, data)
    # Cancelling to_thread does not stop its underlying upload. Keep this independent
    # transaction alive and its row lock held until it settles, including repeated cancellation.
    pending = asyncio.create_task(_replace_avatar(factory, cloud, user_id, content_type, data))
    cancelled = False
    while True:
        try:
            result = await asyncio.shield(pending)
            break
        except asyncio.CancelledError:
            cancelled = True
            if pending.done():
                # A worker cancellation is exceptional; retrieve its result without spinning.
                result = pending.result()
                break
    if cancelled:
        raise asyncio.CancelledError
    return result


async def mark_deleting(db: AsyncSession, user_id: uuid.UUID) -> tuple[uuid.UUID, str]:
    user = await db.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user is None:
        raise AppError(404, "not_found")
    user.status = UserStatus.DELETING
    uid = user.firebase_uid
    await db.commit()
    return user_id, uid


async def finish_deletion(
    factory: async_sessionmaker[AsyncSession], cloud: AccountCloud, user_id: uuid.UUID
) -> None:
    async with factory() as db:
        user = await db.get(User, user_id)
        if user is None or user.status != UserStatus.DELETING:
            return
        uid = user.firebase_uid
        await db.rollback()
        await lock_identity(db, uid)
        user = await db.scalar(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if user is None or user.status != UserStatus.DELETING:
            return
        # Keep the deleting row until both external services have completed.
        await asyncio.to_thread(cloud.delete_files, f"users/{user_id}/")
        await asyncio.to_thread(cloud.delete_user, uid)
        await db.delete(user)
        await db.commit()


async def retry_deletions(factory: async_sessionmaker[AsyncSession], cloud: AccountCloud) -> None:
    """A durable deleting row survives token expiry, crashes and Firebase deletion."""
    while True:
        try:
            async with factory() as db:
                ids = list(
                    await db.scalars(select(User.id).where(User.status == UserStatus.DELETING))
                )
            for user_id in ids:
                try:
                    await finish_deletion(factory, cloud, user_id)
                except Exception:
                    # No UID, token, paths, or user data in operational logs.
                    logger.warning("Account deletion retry failed")
        except Exception:
            logger.warning("Account deletion recovery scan failed")
        await asyncio.sleep(30)


async def revoke_sessions(db: AsyncSession, cloud: AccountCloud, user_id: uuid.UUID) -> None:
    user = await active_user(db, user_id)
    # Persist cutoff before external call: existing ID tokens are rejected even if it fails.
    user.tokens_revoked_at = datetime.now(UTC)
    uid = user.firebase_uid
    await db.commit()
    await asyncio.to_thread(cloud.revoke, uid)
