"""PRD 6.2: 최대 다섯 질문 또는 이해도 100%에서 완료."""

from backend.domain.enums import EndReason

MAX_QUESTIONS = 5


def completion_reason(score: int, answered_questions: int = 1) -> EndReason | None:
    if score == 100:
        return EndReason.UNDERSTOOD
    if answered_questions >= MAX_QUESTIONS:
        return EndReason.MAX_FOLLOWUPS
    return None
