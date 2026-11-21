"""Cuộc trò chuyện một-một và tin nhắn riêng (V3 E4)."""

import os

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "user_a_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "user_b_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("last_message_id", sa.BigInteger()),
        sa.Column("last_message_at", sa.DateTime(timezone=True)),
        sa.Column("a_last_read_id", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("b_last_read_id", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("user_a_id < user_b_id", name="ordered_users"),
        sa.UniqueConstraint("user_a_id", "user_b_id"),
    )
    op.create_index("ix_conversations_user_b_id", "conversations", ["user_b_id"])
    op.create_table(
        "direct_messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sender_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("client_msg_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "deleted_at IS NOT NULL OR char_length(content) BETWEEN 1 AND 2000",
            name="content_length",
        ),
        sa.UniqueConstraint(
            "conversation_id", "sender_id", "client_msg_id", name="uq_direct_messages_client"
        ),
    )
    op.create_index(
        "ix_direct_messages_conversation_id_id",
        "direct_messages",
        ["conversation_id", sa.text("id DESC")],
    )
    if app_role := os.getenv("POSTGRES_APP_USER"):
        role = (
            op.get_context()
            .dialect.identifier_preparer.quote_identifier(app_role)
            .replace("%", "%%")
        )
        op.execute(sa.DDL(f"GRANT SELECT, INSERT, UPDATE ON conversations TO {role}"))
        op.execute(sa.DDL(f"GRANT SELECT, INSERT, UPDATE, DELETE ON direct_messages TO {role}"))
        op.execute(sa.DDL(f"GRANT USAGE ON SEQUENCE direct_messages_id_seq TO {role}"))


def downgrade() -> None:
    op.drop_table("direct_messages")
    op.drop_table("conversations")
