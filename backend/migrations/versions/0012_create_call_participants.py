"""Lịch sử tham gia phòng (V3 E6)."""

import os

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"


def upgrade() -> None:
    op.create_table(
        "call_participants",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "room_id", sa.Uuid(), sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("display_name", sa.String(50), nullable=False),
        sa.Column("is_guest", sa.Boolean(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True)),
        sa.Column("leave_reason", sa.String(16)),
    )
    op.create_index(
        "ix_call_participants_user_joined",
        "call_participants",
        ["user_id", sa.text("joined_at DESC")],
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.create_index(
        "ix_call_participants_room_joined", "call_participants", ["room_id", "joined_at"]
    )
    if app_role := os.getenv("POSTGRES_APP_USER"):
        role = (
            op.get_context()
            .dialect.identifier_preparer.quote_identifier(app_role)
            .replace("%", "%%")
        )
        op.execute(sa.DDL(f"GRANT SELECT, INSERT, UPDATE, DELETE ON call_participants TO {role}"))
        op.execute(sa.DDL(f"GRANT USAGE ON SEQUENCE call_participants_id_seq TO {role}"))
        op.execute(sa.DDL(f"GRANT DELETE ON room_invites, rooms, messages TO {role}"))


def downgrade() -> None:
    if app_role := os.getenv("POSTGRES_APP_USER"):
        role = (
            op.get_context()
            .dialect.identifier_preparer.quote_identifier(app_role)
            .replace("%", "%%")
        )
        op.execute(sa.DDL(f"REVOKE DELETE ON room_invites, rooms, messages FROM {role}"))
    op.drop_table("call_participants")
