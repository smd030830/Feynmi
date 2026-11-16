from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from backend.api.deps import (
    CurrentUser,
    DbSession,
    get_account_cloud,
    get_current_user,
    get_deleting_user,
    require_profile,
)
from backend.db.models import LoginEvent
from backend.domain.enums import QuestionDepth
from backend.errors import AppError
from backend.services import account
from backend.services.cloud import AVATAR_LIMIT, AccountCloud

router = APIRouter(prefix="/me", tags=["account"])
ProfileUser = Annotated[CurrentUser, Depends(require_profile)]
Cloud = Annotated[AccountCloud, Depends(get_account_cloud)]


class SettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    question_depth: QuestionDepth
    notifications_enabled: bool
    weekly_goal_days: int


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_depth: QuestionDepth | None = None
    notifications_enabled: bool | None = None
    weekly_goal_days: Annotated[int, Field(ge=1, le=7, strict=True)] | None = None


@router.get("/settings")
async def get_settings(current: ProfileUser, db: DbSession) -> SettingsResponse:
    await account.active_user(db, current.user.id)
    row = await account.settings(db, current.user.id)
    await db.commit()
    return SettingsResponse.model_validate(row)


@router.patch("/settings")
async def update_settings(
    body: SettingsUpdate, current: ProfileUser, db: DbSession
) -> SettingsResponse:
    await account.active_user(db, current.user.id)
    row = await account.settings(db, current.user.id)
    for name, value in body.model_dump(exclude_unset=True).items():
        if value is None:
            raise AppError(400, "validation_error", "settings cannot be null")
        setattr(row, name, value)
    await db.commit()
    return SettingsResponse.model_validate(row)


class LoginEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    occurred_at: datetime
    client_summary: str


class LoginEventsResponse(BaseModel):
    items: list[LoginEventResponse]


@router.get("/login-events")
async def login_events(current: ProfileUser, db: DbSession) -> LoginEventsResponse:
    rows = await db.scalars(
        select(LoginEvent)
        .where(LoginEvent.user_id == current.user.id)
        .order_by(LoginEvent.occurred_at.desc(), LoginEvent.id.desc())
        .limit(10)
    )
    return LoginEventsResponse(items=[LoginEventResponse.model_validate(row) for row in rows])


@router.post("/login-events", status_code=201)
async def record_login(
    request: Request,
    current: Annotated[CurrentUser, Depends(get_current_user)],
    db: DbSession,
) -> LoginEventResponse:
    await account.active_user(db, current.user.id)
    event = LoginEvent(
        user_id=current.user.id,
        client_summary=account.summarize_agent(request.headers.get("user-agent", "")),
    )
    db.add(event)
    await db.commit()
    return LoginEventResponse.model_validate(event)


@router.post("/revoke-sessions")
async def revoke_sessions(current: ProfileUser, db: DbSession, cloud: Cloud) -> dict[str, bool]:
    try:
        await account.revoke_sessions(db, cloud, current.user.id)
    except AppError:
        raise
    except Exception:
        raise AppError(
            503, "cloud_unavailable", "session revocation failed", retryable=True
        ) from None
    return {"ok": True}


class AvatarResponse(BaseModel):
    avatar_url: str


@router.post("/avatar")
async def avatar_upload(
    request: Request, current: ProfileUser, db: DbSession, cloud: Cloud
) -> AvatarResponse:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type not in ("image/jpeg", "image/png"):
        raise AppError(400, "validation_error", "only JPG and PNG are supported")
    length = request.headers.get("content-length")
    if length is not None and (not length.isdecimal() or int(length) > AVATAR_LIMIT):
        raise AppError(400, "validation_error", "invalid avatar size")
    data = bytearray()
    async for part in request.stream():
        if len(data) + len(part) > AVATAR_LIMIT:
            raise AppError(400, "validation_error", "avatar exceeds size limit")
        data.extend(part)
    user_id = current.user.id
    # Release the read transaction from authentication before the independent mutation.
    await db.rollback()
    try:
        url = await account.replace_avatar(
            request.app.state.session_factory, cloud, user_id, content_type, bytes(data)
        )
    except AppError:
        raise
    except Exception:
        raise AppError(503, "cloud_unavailable", "avatar upload failed", retryable=True) from None
    return AvatarResponse(avatar_url=url)


class DeleteAccount(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: Literal["탈퇴"]


@router.delete("", status_code=204)
async def delete_account(
    body: DeleteAccount,
    request: Request,
    current: Annotated[CurrentUser, Depends(get_deleting_user)],
    db: DbSession,
    cloud: Cloud,
) -> Response:
    user_id, _ = await account.mark_deleting(db, current.user.id)
    try:
        await account.finish_deletion(request.app.state.session_factory, cloud, user_id)
    except Exception:
        raise AppError(
            503, "account_deleting", "deletion will be retried automatically", retryable=True
        ) from None
    return Response(status_code=204)
