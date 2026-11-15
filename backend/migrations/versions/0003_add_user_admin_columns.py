"""Bổ sung quyền và trạng thái tài khoản cho các dòng A2 hiện có."""

import os

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("role", sa.String(16), nullable=False, server_default="user"))
    op.add_column(
        "users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true())
    )
    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True)))
    op.create_check_constraint(op.f("ck_users_role"), "users", "role IN ('user', 'admin')")
    op.create_index(op.f("ix_users_role"), "users", ["role"])
    op.create_index(op.f("ix_users_created_at"), "users", ["created_at"])
    if app_role := os.getenv("POSTGRES_APP_USER"):
        role = op.get_context().dialect.identifier_preparer.quote_identifier(app_role)
        op.execute(sa.DDL(f"GRANT DELETE ON TABLE users TO {role.replace('%', '%%')}"))


def downgrade() -> None:
    if app_role := os.getenv("POSTGRES_APP_USER"):
        role = op.get_context().dialect.identifier_preparer.quote_identifier(app_role)
        op.execute(sa.DDL(f"REVOKE DELETE ON TABLE users FROM {role.replace('%', '%%')}"))
    op.drop_index("ix_users_created_at", table_name="users")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_constraint(op.f("ck_users_role"), "users", type_="check")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "must_change_password")
    op.drop_column("users", "is_active")
    op.drop_column("users", "role")
