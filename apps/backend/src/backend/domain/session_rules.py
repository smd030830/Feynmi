"""PRD 6.2와 FR-2.4: 이해도 100%에서 학습이 완료된다."""

from backend.domain.enums import EndReason


def completion_reason(score: int) -> EndReason | None:
    return EndReason.UNDERSTOOD if score == 100 else None
