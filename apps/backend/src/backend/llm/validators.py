"""입력과 출력의 정합성을 검증한다. 실패는 provider의 재시도 경계로 전달한다."""

from collections.abc import Collection, Sequence
from uuid import UUID

from backend.domain.enums import Importance
from backend.llm.schemas import AssessmentOutput, ConceptExtractionOutput


def _references(labels: Collection[str], allowed: Collection[str]) -> None:
    if not set(labels).issubset(allowed):
        raise ValueError("output references unknown evidence chunks")


def validate_concept_extraction(
    output: ConceptExtractionOutput,
    *,
    chunk_labels: Collection[str],
) -> None:
    for concept in output.concepts:
        if not any(element.importance == Importance.CORE for element in concept.elements):
            raise ValueError("concept must contain a core element")
        for item in [*concept.elements, *concept.misconceptions]:
            _references(item.evidence_chunks, chunk_labels)


def validate_assessment(
    output: AssessmentOutput,
    *,
    element_ids: Collection[UUID],
    chunk_labels: Collection[str],
    learner_answers: Sequence[str],
) -> None:
    ids = [element.element_id for element in output.elements]
    if len(ids) != len(set(ids)) or set(ids) != set(element_ids):
        raise ValueError("each checklist element must be assessed exactly once")
    answers = [" ".join(answer.split()) for answer in learner_answers]

    def quote_exists(quote: str) -> None:
        normalized = " ".join(quote.split())
        if not normalized or not any(normalized in answer for answer in answers):
            raise ValueError("learner quote is not present in session answers")

    for element in output.elements:
        _references(element.evidence_chunks, chunk_labels)
        if element.learner_quote is not None:
            quote_exists(element.learner_quote)
    for statement in output.unverified_statements:
        quote_exists(statement.learner_quote)
