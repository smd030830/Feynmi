"""생성 결과 계약만 정의한다. 개념 추출·평가 업무 흐름은 구현하지 않는다."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from backend.domain.enums import Importance, Verdict

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class OutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExtractedElement(OutputModel):
    text: Text
    importance: Importance
    evidence_chunks: list[Text] = Field(min_length=1)


class ExtractedMisconception(OutputModel):
    text: Text
    evidence_chunks: list[Text] = Field(min_length=1)


class ExtractedConcept(OutputModel):
    title: Text
    description: Text
    elements: list[ExtractedElement] = Field(min_length=3, max_length=5)
    misconceptions: list[ExtractedMisconception] = Field(max_length=2)


class ConceptExtractionOutput(OutputModel):
    concepts: list[ExtractedConcept] = Field(min_length=5, max_length=10)


class ElementAssessment(OutputModel):
    element_id: UUID
    verdict: Verdict
    learner_quote: Text | None
    evidence_chunks: list[Text]
    note: str


class UnverifiedStatement(OutputModel):
    learner_quote: Text
    note: Text


class AssessmentFeedback(OutputModel):
    correct: list[Text]
    missing_hint: list[Text]
    missing: list[Text]
    incorrect: list[Text]
    supplement: str


class AssessmentOutput(OutputModel):
    elements: list[ElementAssessment]
    unverified_statements: list[UnverifiedStatement]
    feedback: AssessmentFeedback
    summary_points: list[Text]
    followup_question: Text | None
