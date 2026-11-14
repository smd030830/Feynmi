"""PRD 6.1③: 상태는 모델의 의견이 아니라 핵심 요소의 판정으로 결정한다."""

from collections.abc import Sequence

from backend.domain.enums import ConceptState, Importance, Verdict


def compute_concept_state(
    has_answer: bool, verdicts: Sequence[tuple[Importance, Verdict]]
) -> ConceptState:
    if not has_answer:
        return ConceptState.NOT_STUDIED
    core = [verdict for importance, verdict in verdicts if importance == Importance.CORE]
    if not core:
        raise ValueError("at least one core element is required")
    if Verdict.CONTRADICTED in core:
        return ConceptState.MISCONCEPTION
    if all(verdict == Verdict.MET for verdict in core):
        return ConceptState.UNDERSTOOD
    return ConceptState.PARTIAL
