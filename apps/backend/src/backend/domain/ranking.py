"""PRD FR-4.3의 취약 개념 순서. DB와 모델 호출에 의존하지 않는다."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from backend.domain.enums import ConceptState


@dataclass(frozen=True)
class RankedConcept:
    id: UUID
    state: ConceptState
    last_assessed_at: datetime | None
    material_created_at: datetime
    ordinal: int


def weakness_key(concept: RankedConcept) -> tuple[int, float, int, str]:
    priority = {
        ConceptState.MISCONCEPTION: 0,
        ConceptState.PARTIAL: 1,
        ConceptState.NOT_STUDIED: 2,
        ConceptState.UNDERSTOOD: 3,
    }
    moment = (
        concept.material_created_at
        if concept.state == ConceptState.NOT_STUDIED
        else concept.last_assessed_at or datetime.min.replace(tzinfo=UTC)
    )
    return priority[concept.state], -moment.timestamp(), concept.ordinal, str(concept.id)
