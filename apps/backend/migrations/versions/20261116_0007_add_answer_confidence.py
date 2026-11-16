"""Store optional answer confidence and link assessments to the triggering answer."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("confidence", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_messages_confidence"),
        "messages",
        "confidence IS NULL OR (role = 'answer' AND confidence IN ('high', 'uncertain', 'low'))",
    )
    op.add_column("assessments", sa.Column("answer_message_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_assessments_answer_message_id_messages"),
        "assessments",
        "messages",
        ["answer_message_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_assessments_answer_message_id_messages"), "assessments", type_="foreignkey"
    )
    op.drop_column("assessments", "answer_message_id")
    op.drop_constraint(op.f("ck_messages_confidence"), "messages", type_="check")
    op.drop_column("messages", "confidence")
