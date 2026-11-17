"""Phân loại phiên đăng nhập và thêm yêu cầu chuyển thiết bị."""

import os

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "refresh_tokens", sa.Column("scope", sa.String(5), server_default="user", nullable=False)
    )
    op.execute("UPDATE refresh_tokens SET revoked_at = NOW() WHERE revoked_at IS NULL")
    op.create_table(
        "device_transfers",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.CHAR(64), nullable=False),
        sa.Column("expected_family", sa.Uuid(), nullable=False),
        sa.Column("use_cookie", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_device_transfers_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_device_transfers")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_device_transfers_token_hash")),
    )
    if app_role := os.getenv("POSTGRES_APP_USER"):
        role = (
            op.get_context()
            .dialect.identifier_preparer.quote_identifier(app_role)
            .replace("%", "%%")
        )
        op.execute(
            sa.DDL(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE device_transfers TO {role}")
        )


def downgrade() -> None:
    op.drop_table("device_transfers")
    op.drop_column("refresh_tokens", "scope")
