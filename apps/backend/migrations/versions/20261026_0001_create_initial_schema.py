"""create initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-26 06:28:10.005759

"""

from collections.abc import Sequence

import pgvector.sqlalchemy.vector
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 자동 생성이 만들지 않는 확장. 임베딩 컬럼(vector)보다 먼저 있어야 한다.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("firebase_uid", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("sign_in_provider", sa.Text(), nullable=False),
        sa.Column("nickname", sa.Text(), nullable=True),
        sa.Column("avatar_path", sa.Text(), nullable=True),
        sa.Column("ai_consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tokens_revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "sign_in_provider IN ('password', 'google.com')", name=op.f("ck_users_sign_in_provider")
        ),
        sa.CheckConstraint("status IN ('active', 'deleting')", name=op.f("ck_users_status")),
        sa.CheckConstraint(
            "nickname IS NULL OR char_length(nickname) BETWEEN 1 AND 20",
            name=op.f("ck_users_nickname"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("firebase_uid", name=op.f("uq_users_firebase_uid")),
    )
    op.create_table(
        "login_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("client_summary", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_login_events_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_login_events")),
    )
    op.create_index(
        "ix_login_events_user_id_occurred_at",
        "login_events",
        ["user_id", sa.literal_column("occurred_at DESC")],
        unique=False,
    )
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("color", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "color IN ('indigo', 'lavender', 'cyan')", name=op.f("ck_projects_color")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_projects_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
    )
    op.create_index(
        "ix_projects_user_id_created_at",
        "projects",
        ["user_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_table(
        "user_settings",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("question_depth", sa.Text(), server_default="basic", nullable=False),
        sa.Column(
            "notifications_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("weekly_goal_days", sa.Integer(), server_default=sa.text("3"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "question_depth IN ('basic', 'deep')", name=op.f("ck_user_settings_question_depth")
        ),
        sa.CheckConstraint(
            "weekly_goal_days BETWEEN 1 AND 7", name=op.f("ck_user_settings_weekly_goal_days")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_settings_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_settings")),
    )
    op.create_table(
        "materials",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("file_type", sa.Text(), nullable=False),
        sa.Column("gcs_path", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), server_default="pending_upload", nullable=False),
        sa.Column("failure_code", sa.Text(), nullable=True),
        sa.Column("analysis_attempt", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "failure_code IS NULL OR failure_code IN ('unsupported_format', 'file_too_large', 'too_many_pages', 'no_extractable_text', 'corrupted_file', 'llm_failed', 'internal_error')",
            name=op.f("ck_materials_failure_code"),
        ),
        sa.CheckConstraint("file_type IN ('pdf', 'pptx')", name=op.f("ck_materials_file_type")),
        sa.CheckConstraint(
            "status IN ('pending_upload', 'queued', 'extracting', 'generating_concepts', 'ready', 'failed')",
            name=op.f("ck_materials_status"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_materials_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_materials")),
    )
    op.create_index(
        "ix_materials_project_id_created_at",
        "materials",
        ["project_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_table(
        "chunks",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("material_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=False),
        sa.Column("page_end", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=1536), nullable=False),
        sa.ForeignKeyConstraint(
            ["material_id"],
            ["materials.id"],
            name=op.f("fk_chunks_material_id_materials"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_chunks_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chunks")),
    )
    op.create_index(
        "ix_chunks_material_id_ordinal", "chunks", ["material_id", "ordinal"], unique=False
    )
    op.create_index("ix_chunks_project_id", "chunks", ["project_id"], unique=False)
    op.create_table(
        "concepts",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("material_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), server_default="not_studied", nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("last_assessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_assessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN ('not_studied', 'partial', 'misconception', 'understood')",
            name=op.f("ck_concepts_state"),
        ),
        sa.CheckConstraint("score BETWEEN 0 AND 100", name=op.f("ck_concepts_score")),
        sa.ForeignKeyConstraint(
            ["material_id"],
            ["materials.id"],
            name=op.f("fk_concepts_material_id_materials"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_concepts")),
    )
    op.create_table(
        "concept_elements",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("concept_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("importance", sa.Text(), nullable=False),
        sa.Column(
            "evidence_chunk_ids",
            sa.ARRAY(sa.Uuid()),
            server_default=sa.text("'{}'::uuid[]"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "importance IN ('core', 'supporting')", name=op.f("ck_concept_elements_importance")
        ),
        sa.ForeignKeyConstraint(
            ["concept_id"],
            ["concepts.id"],
            name=op.f("fk_concept_elements_concept_id_concepts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_concept_elements")),
    )
    op.create_table(
        "concept_misconceptions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("concept_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "evidence_chunk_ids",
            sa.ARRAY(sa.Uuid()),
            server_default=sa.text("'{}'::uuid[]"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["concept_id"],
            ["concepts.id"],
            name=op.f("fk_concept_misconceptions_concept_id_concepts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_concept_misconceptions")),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("concept_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), server_default="in_progress", nullable=False),
        sa.Column("end_reason", sa.Text(), nullable=True),
        sa.Column("followups_used", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("evaluating_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "end_reason IS NULL OR end_reason IN ('understood', 'max_followups', 'user_exit', 'superseded', 'stale')",
            name=op.f("ck_sessions_end_reason"),
        ),
        sa.CheckConstraint(
            "status IN ('in_progress', 'completed', 'aborted')", name=op.f("ck_sessions_status")
        ),
        sa.CheckConstraint("followups_used >= 0", name=op.f("ck_sessions_followups_used")),
        sa.ForeignKeyConstraint(
            ["concept_id"],
            ["concepts.id"],
            name=op.f("fk_sessions_concept_id_concepts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_sessions_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
    )
    op.create_index(
        "uq_sessions_user_id_in_progress",
        "sessions",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'in_progress'"),
    )
    op.create_table(
        "assessments",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("raw_output", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state IN ('partial', 'misconception', 'understood')", name=op.f("ck_assessments_state")
        ),
        sa.CheckConstraint("score BETWEEN 0 AND 100", name=op.f("ck_assessments_score")),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name=op.f("fk_assessments_session_id_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessments")),
        sa.UniqueConstraint("session_id", "seq", name=op.f("uq_assessments_session_id_seq")),
    )
    op.create_index("ix_assessments_created_at", "assessments", ["created_at"], unique=False)
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('answer', 'question')", name=op.f("ck_messages_role")),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name=op.f("fk_messages_session_id_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
        sa.UniqueConstraint("session_id", "seq", name=op.f("uq_messages_session_id_seq")),
    )
    op.create_table(
        "assessment_elements",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("assessment_id", sa.Uuid(), nullable=False),
        sa.Column("element_id", sa.Uuid(), nullable=False),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("learner_quote", sa.Text(), nullable=True),
        sa.Column(
            "evidence_chunk_ids",
            sa.ARRAY(sa.Uuid()),
            server_default=sa.text("'{}'::uuid[]"),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "verdict IN ('met', 'partial', 'missing', 'contradicted')",
            name=op.f("ck_assessment_elements_verdict"),
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            name=op.f("fk_assessment_elements_assessment_id_assessments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["element_id"],
            ["concept_elements.id"],
            name=op.f("fk_assessment_elements_element_id_concept_elements"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessment_elements")),
    )
    op.create_table(
        "feedbacks",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("assessment_id", sa.Uuid(), nullable=False),
        sa.Column(
            "correct",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "missing_hint",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "missing",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "incorrect",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("supplement", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "summary_points",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "unverified_statements",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            name=op.f("fk_feedbacks_assessment_id_assessments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feedbacks")),
        sa.UniqueConstraint("assessment_id", name=op.f("uq_feedbacks_assessment_id")),
    )


def downgrade() -> None:
    op.drop_table("feedbacks")
    op.drop_table("assessment_elements")
    op.drop_table("messages")
    op.drop_index("ix_assessments_created_at", table_name="assessments")
    op.drop_table("assessments")
    op.drop_index(
        "uq_sessions_user_id_in_progress",
        table_name="sessions",
        postgresql_where=sa.text("status = 'in_progress'"),
    )
    op.drop_table("sessions")
    op.drop_table("concept_misconceptions")
    op.drop_table("concept_elements")
    op.drop_table("concepts")
    op.drop_index("ix_chunks_project_id", table_name="chunks")
    op.drop_index("ix_chunks_material_id_ordinal", table_name="chunks")
    op.drop_table("chunks")
    op.drop_index("ix_materials_project_id_created_at", table_name="materials")
    op.drop_table("materials")
    op.drop_table("user_settings")
    op.drop_index("ix_projects_user_id_created_at", table_name="projects")
    op.drop_table("projects")
    op.drop_index("ix_login_events_user_id_occurred_at", table_name="login_events")
    op.drop_table("login_events")
    op.drop_table("users")
    op.execute("DROP EXTENSION IF EXISTS vector")
