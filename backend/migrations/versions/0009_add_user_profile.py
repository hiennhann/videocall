"""Bổ sung hồ sơ, ảnh đại diện và quyền riêng tư (V3 E1)."""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("birth_date", sa.Date()))
    op.add_column("users", sa.Column("avatar_key", sa.String(80)))
    op.add_column("users", sa.Column("avatar_updated_at", sa.DateTime(timezone=True)))
    for name in ("discoverable_by_email", "show_online_status"):
        op.add_column(
            "users", sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.true())
        )
    op.create_check_constraint(
        op.f("ck_users_birth_date"), "users", "birth_date >= DATE '1900-01-01'"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_users_birth_date"), "users", type_="check")
    for name in (
        "show_online_status",
        "discoverable_by_email",
        "avatar_updated_at",
        "avatar_key",
        "birth_date",
    ):
        op.drop_column("users", name)
