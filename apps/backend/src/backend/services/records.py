"""답변이 있는 종료 세션의 기록. 점수는 개념의 현재 값 대신 해당 세션의 마지막 판정을 쓴다."""

import base64
import binascii
import uuid
from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ValidationError
from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Assessment, Concept, Material, Message, Project, Session
from backend.domain.enums import MessageRole, SessionStatus
from backend.errors import AppError


class RecordItem(BaseModel):
    id: uuid.UUID
    concept_id: uuid.UUID
    concept_title: str
    project_id: uuid.UUID
    project_name: str
    started_at: datetime
    ended_at: datetime | None
    score: int | None
    status: SessionStatus


class RecordPage(BaseModel):
    items: list[RecordItem]
    total: int
    next_cursor: str | None


class RecordCursor(BaseModel):
    started_at: AwareDatetime
    id: uuid.UUID


def _decode_cursor(value: str) -> RecordCursor:
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        return RecordCursor.model_validate_json(raw)
    except ValueError, binascii.Error, ValidationError:
        raise AppError(400, "validation_error", "invalid record cursor") from None


def _encode_cursor(item: RecordItem) -> str:
    cursor = RecordCursor(started_at=item.started_at, id=item.id)
    return base64.urlsafe_b64encode(cursor.model_dump_json().encode()).decode().rstrip("=")


async def list_records(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    project_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> RecordPage:
    if project_id is not None and not await db.scalar(
        select(Project.id).where(Project.id == project_id, Project.user_id == user_id)
    ):
        raise AppError(404, "not_found")

    answered = (
        select(Message.id)
        .where(Message.session_id == Session.id, Message.role == MessageRole.ANSWER)
        .exists()
    )
    # 세션과 프로젝트 소유자를 함께 확인해 다른 사용자의 자료가 노출되지 않게 한다.
    query = (
        select(Session.id)
        .join(Concept, Concept.id == Session.concept_id)
        .join(Material, Material.id == Concept.material_id)
        .join(Project, Project.id == Material.project_id)
        .where(
            Session.user_id == user_id,
            Project.user_id == user_id,
            Session.status.in_([SessionStatus.COMPLETED, SessionStatus.ABORTED]),
            answered,
        )
    )
    if project_id is not None:
        query = query.where(Project.id == project_id)
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    if cursor is not None:
        after = _decode_cursor(cursor)
        query = query.where(tuple_(Session.started_at, Session.id) < (after.started_at, after.id))
    last_score = (
        select(Assessment.score)
        .where(Assessment.session_id == Session.id)
        .order_by(Assessment.seq.desc())
        .limit(1)
        .correlate(Session)
        .scalar_subquery()
    )
    rows = await db.execute(
        query.with_only_columns(
            Session.id,
            Session.concept_id,
            Concept.title.label("concept_title"),
            Project.id.label("project_id"),
            Project.name.label("project_name"),
            Session.started_at,
            Session.ended_at,
            Session.status,
            last_score.label("score"),
        )
        .order_by(Session.started_at.desc(), Session.id.desc())
        .limit(limit + 1)
    )
    items = [RecordItem.model_validate(row._mapping) for row in rows]
    has_more = len(items) > limit
    items = items[:limit]
    return RecordPage(
        items=items,
        total=total,
        next_cursor=_encode_cursor(items[-1]) if has_more else None,
    )
