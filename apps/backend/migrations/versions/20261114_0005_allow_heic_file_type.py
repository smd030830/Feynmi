"""allow heic file type (iPhone photos)

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-14 00:00:01

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAME = "ck_materials_file_type"
_BEFORE = "'pdf', 'pptx', 'png', 'jpg', 'txt', 'docx', 'hwp', 'hwpx'"


def upgrade() -> None:
    op.drop_constraint(op.f(_NAME), "materials", type_="check")
    op.create_check_constraint(op.f(_NAME), "materials", f"file_type IN ({_BEFORE}, 'heic')")


def downgrade() -> None:
    # HEIC 자료가 남아 있으면 이전 제약을 걸 수 없으므로 실패한다(데이터를 지우지 않는다).
    op.drop_constraint(op.f(_NAME), "materials", type_="check")
    op.create_check_constraint(op.f(_NAME), "materials", f"file_type IN ({_BEFORE})")
