"""Keep answered sessions when their original concept is deleted."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("archived_project_id", sa.Uuid(), nullable=True))
    op.add_column("sessions", sa.Column("archived_view", JSONB(none_as_null=True), nullable=True))
    op.create_foreign_key(
        op.f("fk_sessions_archived_project_id_projects"),
        "sessions",
        "projects",
        ["archived_project_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(op.f("fk_sessions_concept_id_concepts"), "sessions", type_="foreignkey")
    op.alter_column("sessions", "concept_id", existing_type=sa.Uuid(), nullable=True)
    op.create_foreign_key(
        op.f("fk_sessions_concept_id_concepts"),
        "sessions",
        "concepts",
        ["concept_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Preserve archived learning history instead of discarding it on schema rollback.
    op.execute(
        """
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM sessions WHERE concept_id IS NULL) THEN
                RAISE EXCEPTION 'Cannot downgrade while sessions have no source concept';
            END IF;
        END; $$;
        """
    )
    op.drop_constraint(op.f("fk_sessions_concept_id_concepts"), "sessions", type_="foreignkey")
    op.alter_column("sessions", "concept_id", existing_type=sa.Uuid(), nullable=False)
    op.create_foreign_key(
        op.f("fk_sessions_concept_id_concepts"),
        "sessions",
        "concepts",
        ["concept_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        op.f("fk_sessions_archived_project_id_projects"), "sessions", type_="foreignkey"
    )
    op.drop_column("sessions", "archived_view")
    op.drop_column("sessions", "archived_project_id")
