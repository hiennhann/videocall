"""Lời mời gọi phòng cho bạn bè (V3 E5)."""

import os

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"


def upgrade() -> None:
    op.create_table(
        "room_invites",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "room_id", sa.Uuid(), sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("inviter_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column(
            "invitee_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("responded_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','accepted','declined','expired','cancelled')", name="status"
        ),
    )
    op.create_index("ix_room_invites_room_id", "room_invites", ["room_id"])
    op.create_index("ix_room_invites_inbox", "room_invites", ["invitee_id", "status", "expires_at"])
    op.create_index(
        "uq_room_invites_pending",
        "room_invites",
        ["room_id", "invitee_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    if app_role := os.getenv("POSTGRES_APP_USER"):
        role = (
            op.get_context()
            .dialect.identifier_preparer.quote_identifier(app_role)
            .replace("%", "%%")
        )
        op.execute(sa.DDL(f"GRANT SELECT, INSERT, UPDATE ON room_invites TO {role}"))


def downgrade() -> None:
    op.drop_table("room_invites")
