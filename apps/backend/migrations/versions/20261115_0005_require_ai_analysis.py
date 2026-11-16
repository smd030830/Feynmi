"""Represent missing AI configuration as an analysis failure, including legacy empty results."""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAME = "ck_materials_failure_code"
_BEFORE = (
    "'unsupported_format', 'file_too_large', 'too_many_pages', 'no_extractable_text', "
    "'corrupted_file', 'llm_failed', 'internal_error'"
)


def upgrade() -> None:
    op.drop_constraint(op.f(_NAME), "materials", type_="check")
    op.create_check_constraint(
        op.f(_NAME),
        "materials",
        f"failure_code IS NULL OR failure_code IN ({_BEFORE}, 'ai_unavailable')",
    )
    # A valid completed analysis has at least one concept (PRD FR-1.5).
    # Preserve the original so it can be retried after configuration is restored.
    op.execute(
        "UPDATE materials SET status='failed', failure_code='ai_unavailable', updated_at=now() "
        "WHERE status='ready' AND NOT EXISTS "
        "(SELECT 1 FROM concepts WHERE concepts.material_id=materials.id)"
    )


def downgrade() -> None:
    op.execute("UPDATE materials SET failure_code='llm_failed' WHERE failure_code='ai_unavailable'")
    op.drop_constraint(op.f(_NAME), "materials", type_="check")
    op.create_check_constraint(
        op.f(_NAME), "materials", f"failure_code IS NULL OR failure_code IN ({_BEFORE})"
    )
