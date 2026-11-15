"""Lưu các giá trị cấu hình khác mặc định."""

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "settings",
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("value", JSONB(), nullable=False),
        sa.Column("updated_by", sa.Uuid()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_settings_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_settings")),
    )
    if app_role := os.getenv("POSTGRES_APP_USER"):
        role = op.get_context().dialect.identifier_preparer.quote_identifier(app_role)
        op.execute(
            sa.DDL(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE settings TO {role.replace('%', '%%')}"
            )
        )


def downgrade() -> None:
    op.drop_table("settings")
