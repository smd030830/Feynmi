"""PRD 6.2와 FR-2.4: 최초 설명 뒤 추가 질문은 최대 세 번이다."""

from backend.domain.enums import ConceptState, EndReason

MAX_FOLLOWUPS = 3


def completion_reason(state: ConceptState, followups_used: int) -> EndReason | None:
    if state == ConceptState.UNDERSTOOD:
        return EndReason.UNDERSTOOD
    if followups_used >= MAX_FOLLOWUPS:
        return EndReason.MAX_FOLLOWUPS
    return None
