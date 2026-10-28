from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, StringConstraints

from backend.api.deps import CurrentUser, DbSession, get_current_user, require_verified_email

router = APIRouter(prefix="/me", tags=["me"])


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


def _me_response(current: CurrentUser) -> MeResponse:
    user = current.user
    return MeResponse(
        nickname=user.nickname,
        email=user.email,
        sign_in_provider=user.sign_in_provider,
        email_verified=current.token.email_verified,
        ai_consent_at=user.ai_consent_at,
        avatar_url=None,  # 프로필 이미지(FM-070)에서 Signed URL로 채운다
    )


@router.get("")
async def get_me(current: Annotated[CurrentUser, Depends(get_current_user)]) -> MeResponse:
    # 가입 단계를 이어가려고 인증·닉네임 조건 없이 열어 둔다 (8.1).
    return _me_response(current)


@router.patch("/profile")
async def update_profile(
    body: ProfileUpdate,
    current: Annotated[CurrentUser, Depends(require_verified_email)],
    db: DbSession,
) -> MeResponse:
    # 이메일 가입 ③ 단계, 구글 온보딩, 설정이 함께 쓴다. 닉네임이 아직 없어도 호출할 수 있다.
    current.user.nickname = body.nickname
    await db.commit()
    return _me_response(current)
