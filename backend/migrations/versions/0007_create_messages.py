"""Thêm lịch sử tin nhắn của phòng."""

import os

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid()),
        sa.Column("sender_name", sa.String(50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "char_length(content) BETWEEN 1 AND 2000", name=op.f("ck_messages_content_length")
        ),
        sa.ForeignKeyConstraint(
            ["room_id"], ["rooms.id"], name=op.f("fk_messages_room_id_rooms"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_messages_user_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
    )
    op.create_index("ix_messages_room_id_id", "messages", ["room_id", sa.text("id DESC")])
    if app_role := os.getenv("POSTGRES_APP_USER"):
        role = (
            op.get_context()
            .dialect.identifier_preparer.quote_identifier(app_role)
            .replace("%", "%%")
        )
        op.execute(sa.DDL(f"GRANT SELECT, INSERT ON TABLE messages TO {role}"))
        op.execute(sa.DDL(f"GRANT USAGE ON SEQUENCE messages_id_seq TO {role}"))


def downgrade() -> None:
    op.drop_table("messages")
