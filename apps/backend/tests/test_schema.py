"""스키마 제약을 실제 PostgreSQL에서 확인한다 (architecture.md 9장)."""

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from backend.db.models import (
    Assessment,
    AssessmentElement,
    Base,
    Chunk,
    Concept,
    ConceptElement,
    ConceptMisconception,
    Feedback,
    LoginEvent,
    Material,
    Message,
    Project,
    Session,
    User,
    UserSettings,
)
from backend.db.session import make_session_factory

pytestmark = pytest.mark.usefixtures("migrated_db")

VECTOR = [0.1] * 1536


@dataclass
class Graph:
    user: User
    project: Project
    material: Material
    concept: Concept
    session: Session


def new_user(uid: str = "uid-1", **overrides: object) -> User:
    fields: dict[str, object] = {
        "firebase_uid": uid,
        "email": f"{uid}@example.com",
        "sign_in_provider": "password",
    }
    return User(**{**fields, **overrides})


@pytest.fixture
async def db(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with make_session_factory(engine)() as session:
        yield session
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE users CASCADE"))


def new_assessment(session_id: object, seq: int = 1, **overrides: object) -> Assessment:
    fields: dict[str, object] = {
        "session_id": session_id,
        "seq": seq,
        "state": "partial",
        "score": 50,
        "model_id": "m",
        "raw_output": {},
    }
    return Assessment(**{**fields, **overrides})


async def seed(db: AsyncSession) -> Graph:
    user = new_user()
    db.add(user)
    await db.flush()
    project = Project(user_id=user.id, name="운영체제", color="indigo")
    db.add(project)
    await db.flush()
    material = Material(
        project_id=project.id, title="ch1", file_type="pdf", gcs_path="p", size_bytes=1
    )
    db.add(material)
    await db.flush()
    concept = Concept(material_id=material.id, ordinal=1, title="프로세스", description="d")
    db.add(concept)
    await db.flush()
    session = Session(user_id=user.id, concept_id=concept.id)
    db.add(session)
    await db.flush()
    return Graph(user, project, material, concept, session)


INVALID_ROWS: dict[str, Callable[[Graph], object]] = {
    "sign_in_provider": lambda g: new_user("u2", sign_in_provider="kakao"),
    "user_status": lambda g: new_user("u2", status="banned"),
    "nickname_too_long": lambda g: new_user("u2", nickname="가" * 21),
    "nickname_empty": lambda g: new_user("u2", nickname=""),
    "question_depth": lambda g: UserSettings(user_id=g.user.id, question_depth="hard"),
    "weekly_goal_days": lambda g: UserSettings(user_id=g.user.id, weekly_goal_days=8),
    "project_color": lambda g: Project(user_id=g.user.id, name="p", color="red"),
    "material_file_type": lambda g: Material(
        project_id=g.project.id, title="t", file_type="docx", gcs_path="p", size_bytes=1
    ),
    "material_status": lambda g: Material(
        project_id=g.project.id,
        title="t",
        file_type="pdf",
        gcs_path="p",
        size_bytes=1,
        status="done",
    ),
    "material_failure_code": lambda g: Material(
        project_id=g.project.id,
        title="t",
        file_type="pdf",
        gcs_path="p",
        size_bytes=1,
        failure_code="boom",
    ),
    "concept_state": lambda g: Concept(
        material_id=g.material.id, ordinal=2, title="t", description="d", state="unknown"
    ),
    "concept_score": lambda g: Concept(
        material_id=g.material.id, ordinal=2, title="t", description="d", score=101
    ),
    "element_importance": lambda g: ConceptElement(
        concept_id=g.concept.id, ordinal=1, text="t", importance="minor"
    ),
    "session_status": lambda g: Session(user_id=g.user.id, concept_id=g.concept.id, status="x"),
    "session_end_reason": lambda g: Session(
        user_id=g.user.id, concept_id=g.concept.id, status="aborted", end_reason="x"
    ),
    "message_role": lambda g: Message(session_id=g.session.id, seq=1, role="system", text="t"),
    # 판정이 있으면 답변이 있다는 뜻이므로 not_studied는 올 수 없다 (PRD 6.1③)
    "assessment_not_studied": lambda g: new_assessment(g.session.id, state="not_studied"),
    "assessment_score": lambda g: new_assessment(g.session.id, score=-1),
}


@pytest.mark.parametrize("make", INVALID_ROWS.values(), ids=INVALID_ROWS.keys())
async def test_check_constraints_reject_invalid_values(
    db: AsyncSession, make: Callable[[Graph], object]
) -> None:
    graph = await seed(db)
    db.add(make(graph))
    with pytest.raises(IntegrityError, match="violates check constraint"):
        await db.flush()


async def test_server_defaults(db: AsyncSession) -> None:
    graph = await seed(db)
    settings = UserSettings(user_id=graph.user.id)
    db.add(settings)
    await db.flush()
    for row in (graph.user, settings, graph.material, graph.concept, graph.session):
        await db.refresh(row)

    assert graph.user.status == "active"
    assert (settings.question_depth, settings.notifications_enabled) == ("basic", True)
    assert settings.weekly_goal_days == 3
    assert (graph.material.status, graph.material.analysis_attempt) == ("pending_upload", 0)
    assert (graph.concept.state, graph.concept.score) == ("not_studied", None)
    assert (graph.session.status, graph.session.followups_used) == ("in_progress", 0)


async def test_firebase_uid_is_unique(db: AsyncSession) -> None:
    db.add(new_user("same"))
    await db.flush()
    db.add(new_user("same"))
    with pytest.raises(IntegrityError, match="firebase_uid"):
        await db.flush()


async def test_only_one_in_progress_session_per_user(db: AsyncSession) -> None:
    graph = await seed(db)

    db.add(Session(user_id=graph.user.id, concept_id=graph.concept.id))
    with pytest.raises(IntegrityError, match="uq_sessions_user_id_in_progress"):
        await db.flush()
    await db.rollback()

    # 끝난 세션은 개수 제한에 걸리지 않는다
    graph = await seed(db)
    graph.session.status = "aborted"
    graph.session.end_reason = "superseded"
    await db.flush()
    db.add(Session(user_id=graph.user.id, concept_id=graph.concept.id))
    await db.flush()


async def test_message_and_assessment_seq_unique_per_session(db: AsyncSession) -> None:
    graph = await seed(db)
    db.add(Message(session_id=graph.session.id, seq=1, role="question", text="q"))
    await db.flush()
    db.add(Message(session_id=graph.session.id, seq=1, role="answer", text="a"))
    with pytest.raises(IntegrityError, match="uq_messages_session_id_seq"):
        await db.flush()
    await db.rollback()

    graph = await seed(db)
    db.add(
        Assessment(
            session_id=graph.session.id,
            seq=1,
            state="partial",
            score=50,
            model_id="m",
            raw_output={},
        )
    )
    await db.flush()
    db.add(
        Assessment(
            session_id=graph.session.id,
            seq=1,
            state="partial",
            score=60,
            model_id="m",
            raw_output={},
        )
    )
    with pytest.raises(IntegrityError, match="uq_assessments_session_id_seq"):
        await db.flush()


async def test_embedding_dimension_is_enforced(db: AsyncSession) -> None:
    graph = await seed(db)
    chunk = Chunk(
        material_id=graph.material.id,
        project_id=graph.project.id,
        ordinal=0,
        page_start=1,
        page_end=1,
        text="t",
        token_count=1,
        embedding=VECTOR,
    )
    db.add(chunk)
    await db.flush()
    await db.refresh(chunk)
    assert len(chunk.embedding) == 1536

    db.add(
        Chunk(
            material_id=graph.material.id,
            project_id=graph.project.id,
            ordinal=1,
            page_start=1,
            page_end=1,
            text="t",
            token_count=1,
            embedding=[0.1, 0.2, 0.3],
        )
    )
    with pytest.raises(DBAPIError, match="1536 dimensions"):
        await db.flush()


async def test_deleting_user_removes_all_user_data(db: AsyncSession) -> None:
    """회원 탈퇴는 users 행 삭제 하나로 끝나야 한다 (PRD FR-4.7)."""
    graph = await seed(db)
    db.add_all(
        [
            UserSettings(user_id=graph.user.id),
            LoginEvent(user_id=graph.user.id, client_summary="Chrome · macOS"),
        ]
    )
    chunk = Chunk(
        material_id=graph.material.id,
        project_id=graph.project.id,
        ordinal=0,
        page_start=1,
        page_end=1,
        text="t",
        token_count=1,
        embedding=VECTOR,
    )
    element = ConceptElement(concept_id=graph.concept.id, ordinal=1, text="e", importance="core")
    assessment = new_assessment(graph.session.id)
    db.add_all(
        [
            chunk,
            element,
            assessment,
            ConceptMisconception(concept_id=graph.concept.id, text="m"),
            Message(session_id=graph.session.id, seq=1, role="question", text="q"),
        ]
    )
    await db.flush()
    db.add_all(
        [
            AssessmentElement(
                assessment_id=assessment.id,
                element_id=element.id,
                verdict="met",
                evidence_chunk_ids=[chunk.id],
            ),
            Feedback(assessment_id=assessment.id),
        ]
    )
    await db.flush()

    async def counts() -> dict[str, int]:
        return {
            name: (await db.execute(select(func.count()).select_from(table))).scalar_one()
            for name, table in Base.metadata.tables.items()
        }

    before = await counts()
    assert all(n > 0 for n in before.values()), before  # 14개 테이블 모두에 데이터가 있다

    await db.delete(graph.user)
    await db.flush()
    assert await counts() == dict.fromkeys(before, 0)
