"""사용자 소유 데이터로 학습 통계를 조회한다 (PRD FR-4.9)."""

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Assessment, Concept, Material, Project, Session
from backend.domain.stats import KST, LearningStats, learning_stats


async def load_weekly_days(
    db: AsyncSession, user_id: uuid.UUID, *, today: date | None = None
) -> list[bool]:
    today = today or datetime.now(UTC).astimezone(KST).date()
    monday = today - timedelta(days=today.weekday())
    start = datetime.combine(monday, datetime.min.time(), tzinfo=KST)
    timestamps = await db.scalars(
        select(Assessment.created_at)
        .join(Session, Session.id == Assessment.session_id)
        .where(
            Session.user_id == user_id,
            Assessment.created_at >= start,
            Assessment.created_at < start + timedelta(days=7),
        )
    )
    studied = {stamp.astimezone(KST).date() for stamp in timestamps}
    return [monday + timedelta(days=i) in studied for i in range(7)]


async def load_stats(db: AsyncSession, user_id: uuid.UUID) -> LearningStats:
    timestamps = await db.scalars(
        select(Assessment.created_at)
        .join(Session, Session.id == Assessment.session_id)
        .where(Session.user_id == user_id)
    )
    concepts = await db.execute(
        select(Concept.score, Concept.first_assessed_at)
        .join(Material, Material.id == Concept.material_id)
        .join(Project, Project.id == Material.project_id)
        .where(Project.user_id == user_id)
    )
    return learning_stats(
        timestamps,
        [(row.score, row.first_assessed_at) for row in concepts],
        today=datetime.now(UTC).astimezone(KST).date(),
    )
