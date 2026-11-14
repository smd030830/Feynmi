"""실제 API + PostgreSQL + FakeProvider. 실제 AI/클라우드 계정은 변경하지 않는다."""

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
import pytest
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from backend.api.deps import get_db
from backend.api.sessions import Evaluator, get_evaluator
from backend.auth.firebase import VerifiedToken
from backend.config import Settings
from backend.db.models import (
    Assessment,
    Chunk,
    Concept,
    ConceptElement,
    Material,
    Message,
    Project,
    Session,
    User,
    UserSettings,
)
from backend.db.session import make_session_factory
from backend.domain.enums import Importance, SignInProvider, Verdict
from backend.errors import AppError
from backend.llm.provider import LLMError, LLMTask
from backend.main import create_app

pytestmark = pytest.mark.usefixtures("migrated_db")
URL = "/api/v1"
request_db: ContextVar[AsyncSession] = ContextVar("learning_test_request_db")


class FakeProvider:
    def __init__(self) -> None:
        self.verdict = Verdict.PARTIAL
        self.fail = False
        self.wait: asyncio.Event | None = None
        self.entered = asyncio.Event()
        self.inputs: list[dict[str, Any]] = []
        self.transaction_checks: list[str] = []
        self.omit_quote = False
        self.omit_evidence = False

    def check_transaction(self, phase: str) -> None:
        assert not request_db.get().in_transaction(), f"DB transaction held during {phase}"
        self.transaction_checks.append(phase)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.check_transaction("embedding")
        if self.fail:
            raise LLMError("test failure")
        return [[1.0] + [0.0] * 1535 for _ in texts]

    async def generate_structured[T: BaseModel](
        self,
        *,
        task: LLMTask,
        system: str,
        input: str,
        schema: type[T],
        validate: Callable[[T], None] | None = None,
    ) -> T:
        self.check_transaction("assessment")
        data = json.loads(input)
        self.inputs.append(data)
        self.entered.set()
        if self.wait:
            await self.wait.wait()
        answer = next(m["text"] for m in data["messages"] if m["role"] == "answer")
        output = schema.model_validate(
            {
                "elements": [
                    {
                        "element_id": element["id"],
                        "verdict": self.verdict,
                        "learner_quote": None if self.omit_quote else answer,
                        "evidence_chunks": []
                        if self.omit_evidence
                        else [data["evidence"][0]["label"]],
                        "note": "result-only rationale",
                    }
                    for element in data["checklist"]
                ],
                "unverified_statements": [
                    {"learner_quote": answer, "note": "자료에서 확인되지 않음"}
                ],
                "feedback": {
                    "correct": ["맞은 부분"],
                    "missing_hint": ["힌트"],
                    "missing": ["result-only missing"],
                    "incorrect": ["result-only incorrect"],
                    "supplement": "result-only supplement",
                },
                "summary_points": ["result-only summary"],
                "followup_question": "다른 예를 설명해볼까요?",
            }
        )
        if validate:
            validate(output)
        return output


@dataclass
class Setup:
    client: httpx.AsyncClient
    db: AsyncSession
    provider: FakeProvider
    user_id: UUID
    project_id: UUID
    concept_id: UUID
    next_concept_id: UUID


def auth(uid: str = "alice") -> dict[str, str]:
    return {"Authorization": f"Bearer {uid}"}


@pytest.fixture
async def setup(engine: AsyncEngine) -> AsyncIterator[Setup]:
    factory = make_session_factory(engine)
    async with factory() as db:
        user = User(
            firebase_uid="alice",
            email="alice@example.com",
            sign_in_provider="password",
            nickname="학습자",
        )
        bob = User(
            firebase_uid="bob",
            email="bob@example.com",
            sign_in_provider="password",
            nickname="다른 사용자",
        )
        db.add_all([user, bob])
        await db.flush()
        project = Project(user_id=user.id, name="운영체제", color="indigo")
        db.add(project)
        await db.flush()
        material = Material(
            project_id=project.id,
            title="강의.pdf",
            file_type="pdf",
            gcs_path="unused",
            size_bytes=1,
            status="ready",
        )
        db.add(material)
        await db.flush()
        chunk = Chunk(
            material_id=material.id,
            project_id=project.id,
            ordinal=0,
            page_start=1,
            page_end=2,
            text="프로세스는 실행 중인 프로그램이다.",
            token_count=12,
            embedding=[1.0] + [0.0] * 1535,
        )
        db.add(chunk)
        await db.flush()
        concept = Concept(
            material_id=material.id, ordinal=0, title="프로세스", description="실행 중인 프로그램"
        )
        next_concept = Concept(
            material_id=material.id, ordinal=1, title="스레드", description="실행 단위"
        )
        db.add_all([concept, next_concept])
        await db.flush()
        db.add_all(
            [
                ConceptElement(
                    concept_id=c.id,
                    ordinal=0,
                    text="핵심 요소",
                    importance=Importance.CORE,
                    evidence_chunk_ids=[chunk.id],
                )
                for c in [concept, next_concept]
            ]
        )
        db.add(UserSettings(user_id=user.id, question_depth="deep"))
        await db.commit()

        def verify(uid: str) -> VerifiedToken:
            if uid not in {"alice", "bob"}:
                raise AppError(401, "unauthenticated")
            return VerifiedToken(
                uid, f"{uid}@example.com", True, SignInProvider.PASSWORD, datetime.now(UTC)
            )

        app = create_app(
            Settings(
                database_url=engine.url.render_as_string(hide_password=False),
                firebase_project_id="test",
            ),
            token_verifier=verify,
        )
        provider = FakeProvider()

        async def observed_db() -> AsyncIterator[AsyncSession]:
            async with app.state.session_factory() as request_session:
                token = request_db.set(request_session)
                try:
                    yield request_session
                finally:
                    request_db.reset(token)

        app.dependency_overrides[get_db] = observed_db
        app.dependency_overrides[get_evaluator] = lambda: Evaluator(provider, "test-model")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test", headers=auth()
        ) as client:
            yield Setup(client, db, provider, user.id, project.id, concept.id, next_concept.id)
        await app.state.session_factory.kw["bind"].dispose()


async def start(setup: Setup, concept_id: UUID | None = None) -> str:
    response = await setup.client.post(f"{URL}/concepts/{concept_id or setup.concept_id}/sessions")
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def answer(
    setup: Setup, sid: str, text: str = "프로세스는 실행 중인 작업입니다"
) -> httpx.Response:
    return await setup.client.post(f"{URL}/sessions/{sid}/answers", json={"text": text})


async def test_four_assessments_privacy_cumulative_context_and_result(setup: Setup) -> None:
    listing = await setup.client.get(f"{URL}/projects/{setup.project_id}/concepts")
    assert len(listing.json()["items"]) == 2
    sid = await start(setup)
    view = (await setup.client.get(f"{URL}/sessions/{sid}")).json()
    assert view["messages"][0]["text"] == "먼저 프로세스이(가) 무엇인지 나의 말로 설명해볼까요?"
    assert not setup.provider.inputs
    for attempt in range(4):
        response = await answer(setup, sid, f"설명 {attempt}")
        assert response.status_code == 200, response.text
        body = response.json()
        if attempt < 3:
            assert body["status"] == "in_progress"
            assert body["followups_used"] == attempt + 1
            assert "result-only" not in response.text
            assert "missing" not in body["assessments"][-1]["feedback"]
        else:
            assert body["status"] == "completed"
            assert body["end_reason"] == "max_followups"
    inputs = setup.provider.inputs
    assert inputs[-1]["question_depth"] == "deep"
    assert len([m for m in inputs[-1]["messages"] if m["role"] == "answer"]) == 4
    assert len([m for m in inputs[-1]["messages"] if m["role"] == "question"]) == 4
    result = await setup.client.get(f"{URL}/sessions/{sid}/result")
    assert result.status_code == 200
    body = result.json()
    assert body["score_change"] == 0
    assert body["remaining_core_count"] == 1
    assert body["recommendation"]["concept_id"] == str(setup.next_concept_id)
    assert body["assessments"][-1]["feedback"]["supplement"] == "result-only supplement"
    assert (await answer(setup, sid)).status_code == 409
    concept = await setup.db.get(Concept, setup.concept_id)
    assert concept is not None
    await setup.db.refresh(concept)
    assert concept.score == 50


async def test_understood_ends_immediately_and_relearning_uses_new_context(setup: Setup) -> None:
    sid = await start(setup)
    setup.provider.verdict = Verdict.MET
    response = await answer(setup, sid, "최초 세션의 설명")
    assert response.json()["end_reason"] == "understood"
    assert response.json()["followups_used"] == 0
    second = await start(setup)
    await answer(setup, second, "새 세션의 설명")
    assert "최초 세션의 설명" not in json.dumps(setup.provider.inputs[-1], ensure_ascii=False)
    assert (await setup.client.get(f"{URL}/sessions/{sid}")).json()["status"] == "completed"


async def test_abort_and_supersede_preserve_scores_hide_full_feedback(setup: Setup) -> None:
    sid = await start(setup)
    assessed = await answer(setup, sid)
    assert assessed.status_code == 200, assessed.text
    assert assessed.json()["assessments"][-1]["score"] == 50
    aborted = await setup.client.post(f"{URL}/sessions/{sid}/abort")
    assert aborted.json()["status"] == "aborted"
    assert "result-only" not in aborted.text
    assert (await setup.client.post(f"{URL}/sessions/{sid}/abort")).status_code == 200
    assert (await setup.client.get(f"{URL}/sessions/{sid}/result")).status_code == 409
    second = await start(setup)
    await start(setup, setup.next_concept_id)
    view = (await setup.client.get(f"{URL}/sessions/{second}")).json()
    assert view["end_reason"] == "superseded"
    await setup.db.rollback()
    # The fixture session retains its seeded Concept with expire_on_commit=False.
    # Read the column from PostgreSQL rather than the fixture's stale identity map.
    score = await setup.db.scalar(select(Concept.score).where(Concept.id == setup.concept_id))
    assert score == 50


async def test_failure_retains_answer_unlocks_and_retry_evaluates_cumulatively(
    setup: Setup,
) -> None:
    sid = await start(setup)
    setup.provider.fail = True
    response = await answer(setup, sid, "실패해도 저장할 답변")
    assert response.status_code == 502
    view = (await setup.client.get(f"{URL}/sessions/{sid}")).json()
    assert len(view["messages"]) == 2
    assert not view["assessments"]
    setup.provider.fail = False
    assert (await answer(setup, sid, "다시 제출한 답변")).status_code == 200
    assert len([m for m in setup.provider.inputs[-1]["messages"] if m["role"] == "answer"]) == 2


async def test_ownership_invalid_input_and_not_ready_material(setup: Setup) -> None:
    sid = await start(setup)
    assert (
        await setup.client.get(f"{URL}/projects/{setup.project_id}/concepts", headers=auth("bob"))
    ).status_code == 404
    for method, path, body in [
        ("POST", f"/concepts/{setup.concept_id}/sessions", None),
        ("GET", f"/sessions/{sid}", None),
        ("POST", f"/sessions/{sid}/answers", {"text": "남의 답변"}),
        ("POST", f"/sessions/{sid}/abort", None),
        ("GET", f"/sessions/{sid}/result", None),
    ]:
        response = await setup.client.request(method, URL + path, json=body, headers=auth("bob"))
        assert response.status_code == 404, response.text
    assert (await answer(setup, sid, "   ")).status_code == 400
    assert (await setup.client.get(f"{URL}/sessions/{sid}", headers=auth("bad"))).status_code == 401
    concept = await setup.db.get(Concept, setup.concept_id)
    assert concept is not None
    material = await setup.db.get(Material, concept.material_id)
    assert material is not None
    material.status = "failed"
    await setup.db.commit()
    assert (await answer(setup, sid)).status_code == 409
    response = await setup.client.post(f"{URL}/concepts/{setup.concept_id}/sessions")
    assert response.status_code == 409
    assert (await setup.client.get(f"{URL}/projects/{setup.project_id}/concepts")).json() == {
        "items": [],
        "recommendation": None,
    }


async def test_concurrent_submit_abort_and_start_rejected_during_evaluation(setup: Setup) -> None:
    sid = await start(setup)
    setup.provider.wait = asyncio.Event()
    pending = asyncio.create_task(answer(setup, sid))
    await asyncio.wait_for(setup.provider.entered.wait(), 5)
    try:
        assert (await answer(setup, sid)).json()["error"]["code"] == "evaluation_in_progress"
        assert (await setup.client.post(f"{URL}/sessions/{sid}/abort")).status_code == 409
        assert (
            await setup.client.post(f"{URL}/concepts/{setup.next_concept_id}/sessions")
        ).status_code == 409
    finally:
        setup.provider.wait.set()
        response = await pending
    assert response.status_code == 200, response.text
    await setup.db.rollback()
    assert len(list(await setup.db.scalars(select(Assessment)))) == 1


async def test_stale_evaluator_cannot_overwrite_or_unlock_replacement(setup: Setup) -> None:
    sid = await start(setup)
    setup.provider.wait = asyncio.Event()
    pending = asyncio.create_task(answer(setup, sid))
    await asyncio.wait_for(setup.provider.entered.wait(), 5)
    replacement = datetime.now(UTC) + timedelta(seconds=1)
    row = await setup.db.get(Session, UUID(sid))
    assert row is not None
    row.evaluating_since = replacement
    await setup.db.commit()
    setup.provider.wait.set()
    response = await pending
    assert response.status_code == 409
    await setup.db.refresh(row)
    assert row.evaluating_since == replacement
    assert not list(await setup.db.scalars(select(Assessment)))
    assert len(list(await setup.db.scalars(select(Message).where(Message.role == "answer")))) == 1


async def test_provider_calls_never_hold_database_transactions(setup: Setup) -> None:
    sid = await start(setup)
    response = await answer(setup, sid)
    assert response.status_code == 200, response.text
    assert setup.provider.transaction_checks == ["embedding", "assessment"]


@pytest.mark.parametrize("omitted", ["quote", "evidence"])
async def test_nonmissing_verdict_without_evidence_is_not_saved(setup: Setup, omitted: str) -> None:
    sid = await start(setup)
    setup.provider.omit_quote = omitted == "quote"
    setup.provider.omit_evidence = omitted == "evidence"
    response = await answer(setup, sid)
    assert response.status_code == 502, response.text
    view = (await setup.client.get(f"{URL}/sessions/{sid}")).json()
    assert not view["assessments"]
    assert view["status"] == "in_progress"
    setup.provider.omit_quote = False
    setup.provider.omit_evidence = False
    assert (await answer(setup, sid)).status_code == 200


async def test_missing_verdict_can_have_no_learner_quote(setup: Setup) -> None:
    sid = await start(setup)
    setup.provider.verdict = Verdict.MISSING
    setup.provider.omit_quote = True
    response = await answer(setup, sid)
    assert response.status_code == 200, response.text
    assert response.json()["assessments"][-1]["score"] == 0


async def test_weekly_summary_goal_and_project_scores_follow_assessment(setup: Setup) -> None:
    summary = (await setup.client.get(f"{URL}/me/summary")).json()
    assert summary == {"weekly_goal_days": 3, "study_days": [False] * 7}
    sid = await start(setup)
    assert (await answer(setup, sid)).status_code == 200
    summary = (await setup.client.get(f"{URL}/me/summary")).json()
    today_index = (datetime.now(UTC) + timedelta(hours=9)).weekday()
    assert summary["study_days"] == [i == today_index for i in range(7)]
    assert (await setup.client.get(f"{URL}/me/summary", headers=auth("bob"))).json() == {
        "weekly_goal_days": 3,
        "study_days": [False] * 7,
    }
    changed = await setup.client.patch(f"{URL}/me/settings", json={"weekly_goal_days": 5})
    assert changed.status_code == 200
    assert (await setup.client.get(f"{URL}/me/summary")).json()["weekly_goal_days"] == 5
    project = (await setup.client.get(f"{URL}/projects/{setup.project_id}")).json()
    assert project["score"] == 50
    assert project["state_counts"]["partial"] == 1
    assert project["state_counts"]["not_studied"] == 1
    listing = (await setup.client.get(f"{URL}/projects")).json()
    assert listing["items"][0]["score"] == 50


async def test_home_cleanup_aborts_only_own_idle_or_expired_sessions(setup: Setup) -> None:
    sid = await start(setup)
    # Another user's home must not alter this user's session.
    assert (
        await setup.client.post(f"{URL}/sessions/cleanup", headers=auth("bob"))
    ).status_code == 204
    assert (await setup.client.get(f"{URL}/sessions/{sid}")).json()["status"] == "in_progress"
    response = await setup.client.post(f"{URL}/sessions/cleanup")
    assert response.status_code == 204
    view = (await setup.client.get(f"{URL}/sessions/{sid}")).json()
    assert view["status"] == "aborted" and view["end_reason"] == "stale"
    assert not view["assessments"]
    second = await start(setup)
    row = await setup.db.get(Session, UUID(second))
    assert row is not None
    row.evaluating_since = datetime.now(UTC)
    await setup.db.commit()
    assert (await setup.client.post(f"{URL}/sessions/cleanup")).status_code == 204
    assert (await setup.client.get(f"{URL}/sessions/{second}")).json()["status"] == "in_progress"
    row.evaluating_since = datetime.now(UTC) - timedelta(days=1)
    await setup.db.commit()
    assert (await setup.client.post(f"{URL}/sessions/cleanup")).status_code == 204
    assert (await setup.client.get(f"{URL}/sessions/{second}")).json()["end_reason"] == "stale"


async def test_expired_lease_reclaimed_old_response_cannot_save(setup: Setup) -> None:
    sid = await start(setup)
    gate = asyncio.Event()
    setup.provider.wait = gate
    pending = asyncio.create_task(answer(setup, sid, "오래 걸린 첫 답변"))
    await asyncio.wait_for(setup.provider.entered.wait(), 5)
    try:
        row = await setup.db.get(Session, UUID(sid))
        assert row is not None
        row.evaluating_since = datetime.now(UTC) - timedelta(days=1)
        await setup.db.commit()
        setup.provider.wait = None
        replacement = await answer(setup, sid, "새로운 평가 요청")
        assert replacement.status_code == 200, replacement.text
        assert len(replacement.json()["assessments"]) == 1
        assert len([m for m in replacement.json()["messages"] if m["role"] == "answer"]) == 2
    finally:
        gate.set()
        stale = await pending
    assert stale.status_code == 409
    await setup.db.rollback()
    assert len(list(await setup.db.scalars(select(Assessment)))) == 1
