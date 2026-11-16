"""Store a source-grounded opening question alongside each extracted concept."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing concepts remain intact and use the material-anchored legacy fallback.
    op.add_column("concepts", sa.Column("opening_question", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("concepts", "opening_question")
