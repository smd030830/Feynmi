from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from backend.domain.enums import ConceptState as S
from backend.domain.enums import EndReason, Importance
from backend.domain.enums import Verdict as V
from backend.domain.ranking import RankedConcept, weakness_key
from backend.domain.score_rules import average_score, compute_concept_score
from backend.domain.session_rules import completion_reason
from backend.domain.state_rules import compute_concept_state

CORE, SUPPORT = Importance.CORE, Importance.SUPPORTING


@pytest.mark.parametrize(
    ("answered", "core", "support", "expected"),
    [
        (False, V.CONTRADICTED, V.MET, S.NOT_STUDIED),
        (True, V.CONTRADICTED, V.MET, S.MISCONCEPTION),
        (True, V.MET, V.CONTRADICTED, S.UNDERSTOOD),
        (True, V.PARTIAL, V.MET, S.PARTIAL),
        (True, V.MISSING, V.MET, S.PARTIAL),
    ],
)
def test_state_uses_only_core(answered: bool, core: V, support: V, expected: S) -> None:
    assert compute_concept_state(answered, [(CORE, core), (SUPPORT, support)]) == expected


def test_contradiction_takes_priority_and_score_ignores_supporting() -> None:
    pairs = [(CORE, V.MET), (CORE, V.CONTRADICTED), (SUPPORT, V.MET)]
    assert compute_concept_state(True, pairs) == S.MISCONCEPTION
    assert compute_concept_score(pairs) == 50
    assert compute_concept_score([(CORE, V.PARTIAL), (CORE, V.MET)]) == 75
    assert compute_concept_score([(CORE, V.MET)] + [(CORE, V.MISSING)] * 7) == 13


def test_averages_round_up_exclude_unlearned_and_reject_missing_core() -> None:
    assert average_score([None, 12, 13]) == 13
    assert average_score([None]) is None
    assert average_score([]) is None
    with pytest.raises(ValueError):
        compute_concept_score([(SUPPORT, V.MET)])
    with pytest.raises(ValueError):
        compute_concept_state(True, [])


def test_completion_limits_and_understood_priority() -> None:
    for used in range(3):
        assert completion_reason(S.PARTIAL, used) is None
    assert completion_reason(S.PARTIAL, 3) == EndReason.MAX_FOLLOWUPS
    assert completion_reason(S.UNDERSTOOD, 3) == EndReason.UNDERSTOOD


def test_ranking_state_recency_and_unlearned_ordinal() -> None:
    now = datetime.now(UTC)
    old = now - timedelta(days=1)
    concepts = [
        RankedConcept(uuid4(), S.NOT_STUDIED, None, now, 1),
        RankedConcept(uuid4(), S.PARTIAL, old, now, 0),
        RankedConcept(uuid4(), S.MISCONCEPTION, old, now, 0),
        RankedConcept(uuid4(), S.PARTIAL, now, old, 1),
        RankedConcept(uuid4(), S.NOT_STUDIED, None, now, 0),
        RankedConcept(uuid4(), S.NOT_STUDIED, None, old, 0),
    ]
    assert sorted(concepts, key=weakness_key) == [concepts[i] for i in [2, 3, 1, 4, 0, 5]]
