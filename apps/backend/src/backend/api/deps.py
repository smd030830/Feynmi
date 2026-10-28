"""요청 의존성: DB 세션, 현재 사용자, 인증 조건 (architecture.md 5.2)."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.firebase import TokenVerifier, VerifiedToken
from backend.db.models import User
from backend.errors import AppError

BEARER_PREFIX = "Bearer "


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


def get_token_verifier(request: Request) -> TokenVerifier:
    return request.app.state.token_verifier


DbSession = Annotated[AsyncSession, Depends(get_db)]


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


async def _sync_user(db: AsyncSession, token: VerifiedToken) -> User:
    """`users` 행을 만들거나, 이메일·로그인 수단이 바뀌었으면 맞춘다 (5.2-2)."""
    user = await db.scalar(select(User).where(User.firebase_uid == token.uid))
    provider = token.sign_in_provider.value
    if user and user.email == token.email and user.sign_in_provider == provider:
        return user
    values = {"email": token.email, "sign_in_provider": provider}
    # 같은 사용자의 첫 요청이 동시에 오면 둘 다 행이 없다고 보므로 upsert로 처리한다.
    stmt = (
        insert(User)
        .values(firebase_uid=token.uid, **values)
        .on_conflict_do_update(index_elements=[User.firebase_uid], set_=values)
        .returning(User)
    )
    user = (await db.execute(stmt, execution_options={"populate_existing": True})).scalar_one()
    await db.commit()
    return user


async def get_current_user(
    request: Request,
    db: DbSession,
    verify: Annotated[TokenVerifier, Depends(get_token_verifier)],
) -> CurrentUser:
    token = await asyncio.to_thread(verify, _bearer_token(request))
    user = await _sync_user(db, token)
    # 모든 기기에서 로그아웃한 시각 이전에 로그인한 토큰은 거부한다 (5.2-3).
    if user.tokens_revoked_at and token.auth_time < user.tokens_revoked_at:
        raise AppError(401, "token_revoked", "token was issued before sessions were revoked")
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
