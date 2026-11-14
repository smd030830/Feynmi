"""AI 제공자 대역: 임베딩과 개념 추출 (실제 API를 부르지 않는다)."""

import json
from typing import Any

from backend.domain.enums import Importance
from backend.llm import LLMError, LLMTask
from backend.llm.schemas import (
    ConceptExtractionOutput,
    ExtractedConcept,
    ExtractedElement,
    ExtractedMisconception,
)


def concept_output(labels: list[str], count: int = 5) -> ConceptExtractionOutput:
    """입력에 있는 라벨만 근거로 쓰는 개념 추출 결과 (첫 개념에만 오개념 1개)."""
    first, last = labels[0], labels[-1]
    return ConceptExtractionOutput(
        concepts=[
            ExtractedConcept(
                title=f"개념 {n}",
                description=f"개념 {n}의 기준 설명",
                elements=[
                    ExtractedElement(
                        text=f"핵심 {n}", importance=Importance.CORE, evidence_chunks=[first]
                    ),
                    ExtractedElement(
                        text=f"보충 {n}-1",
                        importance=Importance.SUPPORTING,
                        evidence_chunks=[last, last],  # 같은 근거를 두 번 인용
                    ),
                    ExtractedElement(
                        text=f"보충 {n}-2", importance=Importance.SUPPORTING, evidence_chunks=labels
                    ),
                ],
                misconceptions=(
                    [ExtractedMisconception(text="흔한 오해", evidence_chunks=[first])]
                    if n == 1
                    else []
                ),
            )
            for n in range(1, count + 1)
        ]
    )


class FakeAI:
    """임베딩과 개념 추출을 흉내 낸다. 받은 개념 추출 입력을 기록한다."""

    def __init__(self) -> None:
        self.extraction_inputs: list[dict[str, Any]] = []
        self.fail_extraction = False
        self.concepts = 5
        self.bad_label = False

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0] + [0.0] * 1535 for _ in texts]

    async def generate_structured(self, *, task: LLMTask, input: str, **_: Any) -> Any:
        assert task == LLMTask.CONCEPT_EXTRACTION
        data = json.loads(input)
        self.extraction_inputs.append(data)
        if self.fail_extraction:
            raise LLMError("extraction down")
        labels = [chunk["label"] for chunk in data["chunks"]]
        return concept_output(["C999"] if self.bad_label else labels, self.concepts)
