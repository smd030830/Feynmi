"""PRD 6.1⑥: 핵심 요소만 계산하며 정확히 절반인 값은 올림한다."""

from collections.abc import Iterable, Sequence
from decimal import ROUND_HALF_UP, Decimal

from backend.domain.enums import Importance, Verdict


def _round(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def compute_concept_score(verdicts: Sequence[tuple[Importance, Verdict]]) -> int:
    points = {Verdict.MET: 100, Verdict.PARTIAL: 50, Verdict.MISSING: 0, Verdict.CONTRADICTED: 0}
    core = [points[v] for importance, v in verdicts if importance == Importance.CORE]
    if not core:
        raise ValueError("at least one core element is required")
    return _round(Decimal(sum(core)) / len(core))


def average_score(scores: Iterable[int | None]) -> int | None:
    learned = [score for score in scores if score is not None]
    return _round(Decimal(sum(learned)) / len(learned)) if learned else None
