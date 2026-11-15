"""판정 기록 기반 학습 통계 (PRD FR-4.9, 날짜는 KST)."""

from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from backend.domain.score_rules import average_score

KST = timezone(timedelta(hours=9), name="Asia/Seoul")


class LearningStats(BaseModel):
    overall_score: int | None
    learned_concepts: int
    new_concepts_this_week: int
    study_days_last_30: int
    consecutive_study_days: int


class StudyNotification(BaseModel):
    kind: Literal["goal", "review"]
    message: str
    concept_id: UUID | None = None


def study_notifications(
    *,
    enabled: bool,
    goal_days: int,
    studied_days: int,
    review: tuple[UUID, str] | None,
) -> list[StudyNotification]:
    if not enabled:
        return []
    notifications = []
    if studied_days < goal_days:
        notifications.append(
            StudyNotification(
                kind="goal", message=f"이번 주 목표까지 {goal_days - studied_days}일 남았어요"
            )
        )
    if review is not None:
        concept_id, title = review
        notifications.append(
            StudyNotification(
                kind="review", message=f"{title} 개념을 복습해보세요.", concept_id=concept_id
            )
        )
    return notifications


def learning_stats(
    assessments: Iterable[datetime],
    concepts: Iterable[tuple[int | None, datetime | None]],
    *,
    today: date,
) -> LearningStats:
    days = {stamp.astimezone(KST).date() for stamp in assessments}
    days = {day for day in days if day <= today}
    learned = [(score, first) for score, first in concepts if first is not None]
    monday = today - timedelta(days=today.weekday())
    cursor = today if today in days else today - timedelta(days=1)
    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return LearningStats(
        overall_score=average_score(score for score, _ in learned),
        learned_concepts=len(learned),
        new_concepts_this_week=sum(
            monday <= first.astimezone(KST).date() <= today
            for _, first in learned
            if first is not None
        ),
        study_days_last_30=sum(today - timedelta(days=29) <= day <= today for day in days),
        consecutive_study_days=streak,
    )
