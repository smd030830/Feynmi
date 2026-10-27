"""SQLAlchemy 2.0 모델 (architecture.md 9장).

- ID는 UUID(`gen_random_uuid()`), 시각은 `timestamptz`다.
- 열거형은 PostgreSQL enum이 아니라 `text + CHECK`로 둔다. 허용 값은 `domain.enums`에서 만든다.
- 모든 FK는 `ON DELETE CASCADE`다. 회원 탈퇴는 `users` 행 삭제 하나로 끝난다 (PRD FR-4.7).
- 인덱스는 문서에 정한 것만 둔다. 조회가 생기는 스토리에서 마이그레이션으로 추가한다.
"""

import uuid
from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.domain.enums import (
    ConceptState,
    EndReason,
    FailureCode,
    FileType,
    Importance,
    MaterialStatus,
    MessageRole,
    ProjectColor,
    QuestionDepth,
    SessionStatus,
    SignInProvider,
    UserStatus,
    Verdict,
)

EMBEDDING_DIMENSIONS = 1536  # text-embedding-3-small (PRD 9.2)


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )
    type_annotation_map = {datetime: DateTime(timezone=True)}


def _in(column: str, values: Iterable[StrEnum]) -> str:
    return f"{column} IN ({', '.join(repr(v.value) for v in values)})"


def _enum_check(column: str, enum: type[StrEnum], *, nullable: bool = False) -> CheckConstraint:
    condition = _in(column, enum)
    if nullable:
        condition = f"{column} IS NULL OR {condition}"
    return CheckConstraint(condition, name=column)


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, server_default=text("gen_random_uuid()"))


def _fk(target: str, **kwargs: Any) -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, ForeignKey(target, ondelete="CASCADE"), **kwargs)


def _now() -> Mapped[datetime]:
    return mapped_column(server_default=func.now())


def _updated_at() -> Mapped[datetime]:
    return mapped_column(server_default=func.now(), onupdate=func.now())


def _chunk_ids() -> Mapped[list[uuid.UUID]]:
    return mapped_column(ARRAY(Uuid), server_default=text("'{}'::uuid[]"))


def _json_list() -> Mapped[list[Any]]:
    return mapped_column(JSONB, server_default=text("'[]'::jsonb"))


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        _enum_check("sign_in_provider", SignInProvider),
        _enum_check("status", UserStatus),
        CheckConstraint(
            "nickname IS NULL OR char_length(nickname) BETWEEN 1 AND 20", name="nickname"
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    firebase_uid: Mapped[str] = mapped_column(Text, unique=True)
    email: Mapped[str] = mapped_column(Text)
    sign_in_provider: Mapped[str] = mapped_column(Text)
    nickname: Mapped[str | None] = mapped_column(Text)  # null이면 프로필 미설정
    avatar_path: Mapped[str | None] = mapped_column(Text)
    ai_consent_at: Mapped[datetime | None]
    tokens_revoked_at: Mapped[datetime | None]
    status: Mapped[str] = mapped_column(Text, server_default=UserStatus.ACTIVE.value)
    created_at: Mapped[datetime] = _now()


class UserSettings(Base):
    __tablename__ = "user_settings"
    __table_args__ = (
        _enum_check("question_depth", QuestionDepth),
        CheckConstraint("weekly_goal_days BETWEEN 1 AND 7", name="weekly_goal_days"),
    )

    user_id: Mapped[uuid.UUID] = _fk("users.id", primary_key=True)
    question_depth: Mapped[str] = mapped_column(Text, server_default=QuestionDepth.BASIC.value)
    notifications_enabled: Mapped[bool] = mapped_column(server_default=text("true"))
    weekly_goal_days: Mapped[int] = mapped_column(server_default=text("3"))
    updated_at: Mapped[datetime] = _updated_at()


class LoginEvent(Base):
    __tablename__ = "login_events"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = _fk("users.id")
    occurred_at: Mapped[datetime] = _now()
    client_summary: Mapped[str] = mapped_column(Text)  # 예: "Chrome · macOS". IP는 저장하지 않는다


Index("ix_login_events_user_id_occurred_at", LoginEvent.user_id, LoginEvent.occurred_at.desc())


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (_enum_check("color", ProjectColor),)

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = _fk("users.id")
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _updated_at()


Index("ix_projects_user_id_created_at", Project.user_id, Project.created_at.desc())


class Material(Base):
    __tablename__ = "materials"
    __table_args__ = (
        _enum_check("file_type", FileType),
        _enum_check("status", MaterialStatus),
        _enum_check("failure_code", FailureCode, nullable=True),
    )

    id: Mapped[uuid.UUID] = _pk()
    project_id: Mapped[uuid.UUID] = _fk("projects.id")
    title: Mapped[str] = mapped_column(Text)
    file_type: Mapped[str] = mapped_column(Text)
    gcs_path: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    page_count: Mapped[int | None]  # 워커가 파일을 연 뒤에 채운다 (7.1)
    status: Mapped[str] = mapped_column(Text, server_default=MaterialStatus.PENDING_UPLOAD.value)
    failure_code: Mapped[str | None] = mapped_column(Text)
    analysis_attempt: Mapped[int] = mapped_column(server_default=text("0"))
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _updated_at()


Index("ix_materials_project_id_created_at", Material.project_id, Material.created_at.desc())


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = _pk()
    material_id: Mapped[uuid.UUID] = _fk("materials.id")
    project_id: Mapped[uuid.UUID] = _fk("projects.id")  # 검색 필터용 비정규화 (7.4)
    ordinal: Mapped[int]
    page_start: Mapped[int]
    page_end: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int]
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))


Index("ix_chunks_project_id", Chunk.project_id)
Index("ix_chunks_material_id_ordinal", Chunk.material_id, Chunk.ordinal)


class Concept(Base):
    __tablename__ = "concepts"
    __table_args__ = (
        _enum_check("state", ConceptState),
        CheckConstraint("score BETWEEN 0 AND 100", name="score"),
    )

    id: Mapped[uuid.UUID] = _pk()
    material_id: Mapped[uuid.UUID] = _fk("materials.id")
    ordinal: Mapped[int]
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    # state, score는 평가가 저장될 때 갱신하는 비정규화 값이다 (7.2). score가 null이면 미학습.
    state: Mapped[str] = mapped_column(Text, server_default=ConceptState.NOT_STUDIED.value)
    score: Mapped[int | None]
    last_assessed_at: Mapped[datetime | None]
    first_assessed_at: Mapped[datetime | None]


class ConceptElement(Base):
    __tablename__ = "concept_elements"
    __table_args__ = (_enum_check("importance", Importance),)

    id: Mapped[uuid.UUID] = _pk()
    concept_id: Mapped[uuid.UUID] = _fk("concepts.id")
    ordinal: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    importance: Mapped[str] = mapped_column(Text)
    evidence_chunk_ids: Mapped[list[uuid.UUID]] = _chunk_ids()


class ConceptMisconception(Base):
    __tablename__ = "concept_misconceptions"

    id: Mapped[uuid.UUID] = _pk()
    concept_id: Mapped[uuid.UUID] = _fk("concepts.id")
    text: Mapped[str] = mapped_column(Text)
    evidence_chunk_ids: Mapped[list[uuid.UUID]] = _chunk_ids()


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        _enum_check("status", SessionStatus),
        _enum_check("end_reason", EndReason, nullable=True),
        CheckConstraint("followups_used >= 0", name="followups_used"),
    )

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = _fk("users.id")
    concept_id: Mapped[uuid.UUID] = _fk("concepts.id")
    status: Mapped[str] = mapped_column(Text, server_default=SessionStatus.IN_PROGRESS.value)
    end_reason: Mapped[str | None] = mapped_column(Text)
    followups_used: Mapped[int] = mapped_column(server_default=text("0"))
    evaluating_since: Mapped[datetime | None]  # 평가 잠금 (7.2)
    started_at: Mapped[datetime] = _now()
    ended_at: Mapped[datetime | None]


# 사용자당 진행 중 세션은 하나다 (PRD 6.2)
Index(
    "uq_sessions_user_id_in_progress",
    Session.user_id,
    unique=True,
    postgresql_where=text(f"status = '{SessionStatus.IN_PROGRESS.value}'"),
)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("session_id", "seq"),
        _enum_check("role", MessageRole),
    )

    id: Mapped[uuid.UUID] = _pk()
    session_id: Mapped[uuid.UUID] = _fk("sessions.id")
    seq: Mapped[int]
    role: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()


class Assessment(Base):
    __tablename__ = "assessments"
    __table_args__ = (
        UniqueConstraint("session_id", "seq"),
        # 판정이 있다는 것은 답변이 있다는 뜻이므로 `not_studied`는 올 수 없다 (PRD 6.1③).
        CheckConstraint(
            _in("state", [s for s in ConceptState if s is not ConceptState.NOT_STUDIED]),
            name="state",
        ),
        CheckConstraint("score BETWEEN 0 AND 100", name="score"),
    )

    id: Mapped[uuid.UUID] = _pk()
    session_id: Mapped[uuid.UUID] = _fk("sessions.id")
    seq: Mapped[int]
    state: Mapped[str] = mapped_column(Text)
    score: Mapped[int]
    model_id: Mapped[str] = mapped_column(Text)
    raw_output: Mapped[dict[str, Any]] = mapped_column(JSONB)  # 판정 품질 점검용
    created_at: Mapped[datetime] = _now()


Index("ix_assessments_created_at", Assessment.created_at)  # 학습 통계 (7.5)


class AssessmentElement(Base):
    __tablename__ = "assessment_elements"
    __table_args__ = (_enum_check("verdict", Verdict),)

    id: Mapped[uuid.UUID] = _pk()
    assessment_id: Mapped[uuid.UUID] = _fk("assessments.id")
    element_id: Mapped[uuid.UUID] = _fk("concept_elements.id")
    verdict: Mapped[str] = mapped_column(Text)
    learner_quote: Mapped[str | None] = mapped_column(Text)
    evidence_chunk_ids: Mapped[list[uuid.UUID]] = _chunk_ids()
    note: Mapped[str | None] = mapped_column(Text)


class Feedback(Base):
    __tablename__ = "feedbacks"

    id: Mapped[uuid.UUID] = _pk()
    assessment_id: Mapped[uuid.UUID] = _fk("assessments.id", unique=True)
    correct: Mapped[list[Any]] = _json_list()
    missing_hint: Mapped[list[Any]] = _json_list()
    missing: Mapped[list[Any]] = _json_list()
    incorrect: Mapped[list[Any]] = _json_list()
    supplement: Mapped[str] = mapped_column(Text, server_default="")
    summary_points: Mapped[list[Any]] = _json_list()
    unverified_statements: Mapped[list[Any]] = _json_list()
