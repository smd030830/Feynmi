from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.api.deps import CurrentUser, DbSession, require_profile
from backend.api.projects import ProjectResponse, _project_response
from backend.db.models import UserSettings
from backend.domain.enums import ConceptState, ProjectColor
from backend.domain.stats import LearningStats, StudyNotification, study_notifications
from backend.services import projects, sessions
from backend.services.stats import load_stats, load_weekly_days

router = APIRouter(tags=["home"])


class HomeResponse(BaseModel):
    stats: LearningStats
    projects: list[ProjectResponse]
    next_color: ProjectColor
    recommendation: dict[str, Any] | None
    weak_concepts: list[dict[str, Any]]
    notifications: list[StudyNotification]


@router.get("/home")
async def get_home(
    current: Annotated[CurrentUser, Depends(require_profile)], db: DbSession
) -> HomeResponse:
    # 조회 전에 누락된 이탈을 처리하고, 유효한 평가 잠금은 기존 규칙으로 보호한다.
    await sessions.cleanup_on_home(db, current.user.id)
    summaries = await projects.list_projects(db, current.user.id)
    weak = await sessions.weak_concepts(db, current.user.id)
    settings = await db.get(UserSettings, current.user.id)
    enabled = settings.notifications_enabled if settings else True
    review = (
        weak[0]
        if weak and weak[0]["state"] in (ConceptState.MISCONCEPTION, ConceptState.PARTIAL)
        else None
    )
    notifications = study_notifications(
        enabled=enabled,
        goal_days=settings.weekly_goal_days if settings else 3,
        studied_days=sum(await load_weekly_days(db, current.user.id)) if enabled else 0,
        review=(review["concept_id"], review["concept_title"]) if review else None,
    )
    return HomeResponse(
        stats=await load_stats(db, current.user.id),
        projects=[_project_response(summary) for summary in summaries],
        next_color=await projects.next_color(db, current.user.id),
        recommendation=weak[0] if weak else None,
        weak_concepts=weak,
        notifications=notifications,
    )
