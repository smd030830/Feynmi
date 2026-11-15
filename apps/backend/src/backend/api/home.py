from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.api.deps import CurrentUser, DbSession, require_profile
from backend.api.projects import ProjectResponse, _project_response
from backend.domain.enums import ProjectColor
from backend.domain.stats import LearningStats
from backend.services import projects, sessions
from backend.services.stats import load_stats

router = APIRouter(tags=["home"])


class HomeResponse(BaseModel):
    stats: LearningStats
    projects: list[ProjectResponse]
    next_color: ProjectColor
    recommendation: dict[str, Any] | None


@router.get("/home")
async def get_home(
    current: Annotated[CurrentUser, Depends(require_profile)], db: DbSession
) -> HomeResponse:
    # 조회 전에 누락된 이탈을 처리하고, 유효한 평가 잠금은 기존 규칙으로 보호한다.
    await sessions.cleanup_on_home(db, current.user.id)
    summaries = await projects.list_projects(db, current.user.id)
    return HomeResponse(
        stats=await load_stats(db, current.user.id),
        projects=[_project_response(summary) for summary in summaries],
        next_color=await projects.next_color(db, current.user.id),
        recommendation=await sessions._recommendation(db, current.user.id),
    )
