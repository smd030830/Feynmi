"""프로젝트 규칙 (PRD FR-1.0)."""

from backend.domain.enums import ProjectColor

COLOR_ORDER = (ProjectColor.INDIGO, ProjectColor.LAVENDER, ProjectColor.CYAN)


def next_project_color(project_count: int) -> ProjectColor:
    """사용자가 가진 프로젝트 수로 다음 색을 순환 배정한다 (architecture.md 9장)."""
    return COLOR_ORDER[project_count % len(COLOR_ORDER)]
