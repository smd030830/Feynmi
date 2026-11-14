"""프로젝트 유스케이스 (PRD FR-1.0, architecture.md 8.1).

모든 조회는 `user_id`로 범위를 좁힌다. 다른 사용자의 프로젝트는 없는 것처럼 404로 처리한다 (5.2-7).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Concept, Material, Project
from backend.domain.enums import ConceptState, ProjectColor
from backend.domain.projects import next_project_color
from backend.domain.score_rules import average_score
from backend.errors import AppError
from backend.services.account import active_user

StateCounts = dict[ConceptState, int]


@dataclass(frozen=True)
class ProjectSummary:
    project: Project
    state_counts: StateCounts
    material_count: int
    score: int | None = None


def _empty_counts() -> StateCounts:
    return dict.fromkeys(ConceptState, 0)


async def _count_projects(db: AsyncSession, user_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(Project).where(Project.user_id == user_id)
    return await db.scalar(stmt) or 0


async def next_color(db: AsyncSession, user_id: uuid.UUID) -> ProjectColor:
    return next_project_color(await _count_projects(db, user_id))


async def create_project(
    db: AsyncSession, user_id: uuid.UUID, name: str, description: str | None
) -> ProjectSummary:
    # 탈퇴 표시와 직렬화하여 삭제가 시작된 계정의 새 데이터 생성을 차단한다.
    await active_user(db, user_id)
    color = await next_color(db, user_id)
    project = Project(user_id=user_id, name=name, description=description, color=color.value)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return ProjectSummary(project, _empty_counts(), material_count=0)


async def _summaries(db: AsyncSession, projects: Sequence[Project]) -> list[ProjectSummary]:
    """프로젝트별 개념 상태 분포와 자료 수를 한 번에 센다 (7.5)."""
    ids = [p.id for p in projects]
    counts = {pid: _empty_counts() for pid in ids}
    state_rows = await db.execute(
        select(Material.project_id, Concept.state, func.count())
        .join(Concept, Concept.material_id == Material.id)
        .where(Material.project_id.in_(ids))
        .group_by(Material.project_id, Concept.state)
    )
    for pid, state, n in state_rows:
        counts[pid][ConceptState(state)] = n

    material_rows = await db.execute(
        select(Material.project_id, func.count())
        .where(Material.project_id.in_(ids))
        .group_by(Material.project_id)
    )
    materials: dict[uuid.UUID, int] = {pid: n for pid, n in material_rows}
    score_rows = await db.execute(
        select(Material.project_id, Concept.score)
        .join(Concept, Concept.material_id == Material.id)
        .where(Material.project_id.in_(ids))
    )
    scores: dict[uuid.UUID, list[int | None]] = {pid: [] for pid in ids}
    for pid, score in score_rows:
        scores[pid].append(score)
    return [
        ProjectSummary(p, counts[p.id], materials.get(p.id, 0), average_score(scores[p.id]))
        for p in projects
    ]


async def list_projects(db: AsyncSession, user_id: uuid.UUID) -> list[ProjectSummary]:
    # 최근 학습순 정렬(design-system 9.9)은 세션이 생기면(FM-030) 바꾼다. 지금은 최신 생성순이다.
    projects = await db.scalars(
        select(Project).where(Project.user_id == user_id).order_by(Project.created_at.desc())
    )
    return await _summaries(db, projects.all())


async def get_project(
    db: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID
) -> ProjectSummary:
    project = await db.scalar(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    if project is None:
        raise AppError(404, "not_found", "project not found")
    [summary] = await _summaries(db, [project])
    return summary
