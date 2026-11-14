import asyncio
from datetime import UTC, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, StringConstraints
from sqlalchemy import select

from backend.api.deps import (
    CurrentUser,
    DbSession,
    get_account_cloud,
    get_current_user,
    require_profile,
    require_verified_email,
)
from backend.db.models import Assessment, Session, UserSettings
from backend.services.account import active_user
from backend.services.cloud import AccountCloud

router = APIRouter(prefix="/me", tags=["me"])

KST = timezone(timedelta(hours=9), name="Asia/Seoul")


class WeeklySummary(BaseModel):
    weekly_goal_days: int
    study_days: list[bool]


@router.get("/summary")
async def get_summary(
    current: Annotated[CurrentUser, Depends(require_profile)],
    db: DbSession,
) -> WeeklySummary:
    today = datetime.now(UTC).astimezone(KST).date()
    monday = today - timedelta(days=today.weekday())
    start = datetime.combine(monday, datetime.min.time(), tzinfo=KST)
    timestamps = await db.scalars(
        select(Assessment.created_at)
        .join(Session, Session.id == Assessment.session_id)
        .where(
            Session.user_id == current.user.id,
            Assessment.created_at >= start,
            Assessment.created_at < start + timedelta(days=7),
        )
    )
    studied = {stamp.astimezone(KST).date() for stamp in timestamps}
    settings = await db.get(UserSettings, current.user.id)
    return WeeklySummary(
        weekly_goal_days=settings.weekly_goal_days if settings else 3,
        study_days=[monday + timedelta(days=i) in studied for i in range(7)],
    )


class MeResponse(BaseModel):
    nickname: str | None
    email: str
    sign_in_provider: str
    email_verified: bool
    ai_consent_at: datetime | None
    avatar_url: str | None


class ProfileUpdate(BaseModel):
    # 1~20자 (PRD FR-4.1). 앞뒤 공백은 지운다.
    nickname: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]


async def _me_response(current: CurrentUser, cloud: AccountCloud) -> MeResponse:
    user = current.user
    return MeResponse(
        nickname=user.nickname,
        email=user.email,
        sign_in_provider=user.sign_in_provider,
        email_verified=current.token.email_verified,
        ai_consent_at=user.ai_consent_at,
        avatar_url=await asyncio.to_thread(cloud.read_url, user.avatar_path)
        if user.avatar_path
        else None,
    )


@router.get("")
async def get_me(
    current: Annotated[CurrentUser, Depends(get_current_user)],
    cloud: Annotated[AccountCloud, Depends(get_account_cloud)],
) -> MeResponse:
    # 가입 단계를 이어가려고 인증·닉네임 조건 없이 열어 둔다 (8.1).
    return await _me_response(current, cloud)


@router.patch("/profile")
async def update_profile(
    body: ProfileUpdate,
    current: Annotated[CurrentUser, Depends(require_verified_email)],
    db: DbSession,
    cloud: Annotated[AccountCloud, Depends(get_account_cloud)],
) -> MeResponse:
    # 이메일 가입 ③ 단계, 구글 온보딩, 설정이 함께 쓴다. 닉네임이 아직 없어도 호출할 수 있다.
    user = await active_user(db, current.user.id)
    user.nickname = body.nickname
    await db.commit()
    return await _me_response(current, cloud)
