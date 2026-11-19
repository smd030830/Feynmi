"""Keep archived learning records after project deletion."""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("fk_sessions_archived_project_id_projects"), "sessions", type_="foreignkey"
    )


def downgrade() -> None:
    # Refuse to reintroduce a cascading FK if it would invalidate preserved history.
    op.execute(
        """DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM sessions s WHERE s.archived_project_id IS NOT NULL
                   AND NOT EXISTS (SELECT 1 FROM projects p WHERE p.id = s.archived_project_id))
        THEN RAISE EXCEPTION 'Cannot downgrade while records have deleted projects';
        END IF;
        END; $$;"""
    )
    op.create_foreign_key(
        op.f("fk_sessions_archived_project_id_projects"),
        "sessions",
        "projects",
        ["archived_project_id"],
        ["id"],
        ondelete="CASCADE",
    )
