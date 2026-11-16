"""allow text document file types (txt, docx, hwp, hwpx)

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-14 00:00:00

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAME = "ck_materials_file_type"


def upgrade() -> None:
    op.drop_constraint(op.f(_NAME), "materials", type_="check")
    op.create_check_constraint(
        op.f(_NAME),
        "materials",
        "file_type IN ('pdf', 'pptx', 'png', 'jpg', 'txt', 'docx', 'hwp', 'hwpx')",
    )


def downgrade() -> None:
    # 새 형식 자료가 남아 있으면 이전 제약을 걸 수 없으므로 실패한다(데이터를 지우지 않는다).
    op.drop_constraint(op.f(_NAME), "materials", type_="check")
    op.create_check_constraint(
        op.f(_NAME), "materials", "file_type IN ('pdf', 'pptx', 'png', 'jpg')"
    )
