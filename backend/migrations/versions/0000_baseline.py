"""Baseline trước khi có các bảng nghiệp vụ."""

from collections.abc import Sequence

revision: str = "0000"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Ghi nhận revision đầu tiên mà không tạo bảng nghiệp vụ."""


def downgrade() -> None:
    """Lùi về trạng thái trước revision đầu tiên."""
