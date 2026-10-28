from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.api.deps import CurrentUser, get_current_user

router = APIRouter(prefix="/me", tags=["me"])


class MeResponse(BaseModel):
    nickname: str | None
    email: str
    sign_in_provider: str
    email_verified: bool
    ai_consent_at: datetime | None
    avatar_url: str | None


@router.get("")
async def get_me(current: Annotated[CurrentUser, Depends(get_current_user)]) -> MeResponse:
    # 가입 단계를 이어가려고 인증·닉네임 조건 없이 열어 둔다 (8.1).
    user = current.user
    return MeResponse(
        nickname=user.nickname,
        email=user.email,
        sign_in_provider=user.sign_in_provider,
        email_verified=current.token.email_verified,
        ai_consent_at=user.ai_consent_at,
        avatar_url=None,  # 프로필 이미지(FM-070)에서 Signed URL로 채운다
    )
