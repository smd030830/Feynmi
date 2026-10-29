import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, StringConstraints

from backend.api.deps import CurrentUser, DbSession, require_profile
from backend.domain.enums import ConceptState, ProjectColor
from backend.services import projects
from backend.services.projects import ProjectSummary

router = APIRouter(prefix="/projects", tags=["projects"])

ProfileUser = Annotated[CurrentUser, Depends(require_profile)]

# PRD FR-1.0
NAME_MAX_LENGTH = 40
DESCRIPTION_MAX_LENGTH = 200


class ProjectCreate(BaseModel):
    # 앞뒤 공백은 지운다. 설명이 공백뿐이면 없는 것으로 본다.
    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_MAX_LENGTH)
    ]
    description: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=DESCRIPTION_MAX_LENGTH)]
        | None
    ) = None


class StateCounts(BaseModel):
    understood: int
    partial: int
    misconception: int
    not_studied: int


class ProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    color: ProjectColor
    score: int | None  # 프로젝트 이해도. null이면 학습한 개념이 없다
    state_counts: StateCounts
    material_count: int
    created_at: datetime


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]
    next_color: ProjectColor  # 새 프로젝트 모달의 미리보기 색 (design-system 9.8)


def _project_response(summary: ProjectSummary) -> ProjectResponse:
    project = summary.project
    counts = summary.state_counts
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        color=ProjectColor(project.color),
        score=None,  # 평균 규칙(FM-036)이 생기면 concepts.score로 계산한다
        state_counts=StateCounts(
            understood=counts[ConceptState.UNDERSTOOD],
            partial=counts[ConceptState.PARTIAL],
            misconception=counts[ConceptState.MISCONCEPTION],
            not_studied=counts[ConceptState.NOT_STUDIED],
        ),
        material_count=summary.material_count,
        created_at=project.created_at,
    )


@router.get("")
async def list_projects(current: ProfileUser, db: DbSession) -> ProjectListResponse:
    summaries = await projects.list_projects(db, current.user.id)
    return ProjectListResponse(
        items=[_project_response(s) for s in summaries],
        next_color=await projects.next_color(db, current.user.id),
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate, current: ProfileUser, db: DbSession
) -> ProjectResponse:
    summary = await projects.create_project(
        db, current.user.id, body.name, body.description or None
    )
    return _project_response(summary)


@router.get("/{project_id}")
async def get_project(
    project_id: uuid.UUID, current: ProfileUser, db: DbSession
) -> ProjectResponse:
    # 최근 학습 3건(architecture.md 8.1)은 세션 기록(FM-044)에서 추가한다.
    return _project_response(await projects.get_project(db, current.user.id, project_id))
