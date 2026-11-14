"""요청 의존성: DB 세션, 현재 사용자, 인증 조건 (architecture.md 5.2)."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.firebase import TokenVerifier, VerifiedToken
from backend.db.models import User
from backend.domain.enums import UserStatus
from backend.errors import AppError
from backend.services.account import lock_identity
from backend.services.cloud import AccountCloud, GoogleAccountCloud

BEARER_PREFIX = "Bearer "


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


def get_token_verifier(request: Request) -> TokenVerifier:
    return request.app.state.token_verifier


DbSession = Annotated[AsyncSession, Depends(get_db)]


def get_account_cloud(request: Request) -> AccountCloud:
    cloud = getattr(request.app.state, "account_cloud", None)
    if cloud is not None:
        return cloud
    from backend.config import get_settings

    settings = get_settings()
    cloud = GoogleAccountCloud(
        settings.firebase_project_id, settings.gcs_bucket, settings.gcs_signer_service_account
    )
    request.app.state.account_cloud = cloud
    return cloud


@dataclass(frozen=True)
class CurrentUser:
    user: User
    token: VerifiedToken


def _bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    token = header[len(BEARER_PREFIX) :].strip() if header.startswith(BEARER_PREFIX) else ""
    if not token:
        raise AppError(401, "unauthenticated", "missing bearer token")
    return token


async def _sync_user(db: AsyncSession, token: VerifiedToken, cloud: AccountCloud) -> User:
    """`users` 행을 만들거나, 이메일·로그인 수단이 바뀌었으면 맞춘다 (5.2-2)."""
    user = await db.scalar(select(User).where(User.firebase_uid == token.uid))
    if user is not None and user.status == UserStatus.DELETING:
        raise AppError(409, "account_deleting", "account deletion is in progress")
    if user is None:
        # Deleted Firebase users can retain signature-valid JWTs until expiry.
        # Serialize first provisioning against final deletion before checking existence.
        await lock_identity(db, token.uid)
        user = await db.scalar(select(User).where(User.firebase_uid == token.uid))
        if user is None:
            await asyncio.to_thread(cloud.check_user, token)
        elif user.status == UserStatus.DELETING:
            raise AppError(409, "account_deleting", "account deletion is in progress")
    provider = token.sign_in_provider.value
    if user and user.email == token.email and user.sign_in_provider == provider:
        return user
    values = {"email": token.email, "sign_in_provider": provider}
    if user is not None:
        # A known row must never become an INSERT: deletion may finish after the read.
        # Updating its immutable ID cannot recreate an already deleted Firebase identity.
        user = (
            await db.execute(
                update(User)
                .where(User.id == user.id, User.status == UserStatus.ACTIVE)
                .values(**values)
                .returning(User),
                execution_options={"populate_existing": True},
            )
        ).scalar_one_or_none()
        if user is None:
            raise AppError(409, "account_deleting", "account no longer active")
        await db.commit()
        return user
    # 같은 사용자의 첫 요청이 동시에 오면 둘 다 행이 없다고 보므로 upsert로 처리한다.
    stmt = (
        insert(User)
        .values(firebase_uid=token.uid, **values)
        .on_conflict_do_update(
            index_elements=[User.firebase_uid], set_=values, where=User.status == UserStatus.ACTIVE
        )
        .returning(User)
    )
    user = (
        await db.execute(stmt, execution_options={"populate_existing": True})
    ).scalar_one_or_none()
    if user is None:
        raise AppError(409, "account_deleting", "account deletion is in progress")
    await db.commit()
    return user


async def get_current_user(
    request: Request,
    db: DbSession,
    verify: Annotated[TokenVerifier, Depends(get_token_verifier)],
    cloud: Annotated[AccountCloud, Depends(get_account_cloud)],
) -> CurrentUser:
    token = await asyncio.to_thread(verify, _bearer_token(request))
    user = await _sync_user(db, token, cloud)
    # 모든 기기에서 로그아웃한 시각 이전에 로그인한 토큰은 거부한다 (5.2-3).
    if user.tokens_revoked_at and token.auth_time < user.tokens_revoked_at:
        raise AppError(401, "token_revoked", "token was issued before sessions were revoked")
    return CurrentUser(user=user, token=token)


async def get_deleting_user(
    request: Request,
    db: DbSession,
    verify: Annotated[TokenVerifier, Depends(get_token_verifier)],
) -> CurrentUser:
    """Deletion retries never provision a new user or need a live Firebase account."""
    token = await asyncio.to_thread(verify, _bearer_token(request))
    user = await db.scalar(select(User).where(User.firebase_uid == token.uid))
    if user is None:
        raise AppError(404, "not_found", "account no longer exists")
    if user.status != UserStatus.DELETING:
        if user.tokens_revoked_at and token.auth_time < user.tokens_revoked_at:
            raise AppError(401, "token_revoked")
        if not token.email_verified or not user.nickname:
            raise AppError(403, "profile_required")
    return CurrentUser(user=user, token=token)


def require_verified_email(
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    if not current.token.email_verified:
        raise AppError(403, "email_not_verified", "email is not verified")
    return current


def require_profile(
    current: Annotated[CurrentUser, Depends(require_verified_email)],
) -> CurrentUser:
    """이메일 인증과 닉네임 설정을 모두 마친 "사용자 API" 조건 (8.1)."""
    if not current.user.nickname:
        raise AppError(403, "profile_required", "nickname is not set")
    return current
