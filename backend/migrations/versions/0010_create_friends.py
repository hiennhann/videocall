"""Lời mời kết bạn, quan hệ chuẩn hóa và chặn một chiều (V3 E2)."""

import os

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "friend_requests",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("from_user_id", sa.Uuid(), nullable=False),
        sa.Column("to_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("responded_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "from_user_id <> to_user_id", name=op.f("ck_friend_requests_different_users")
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'declined', 'cancelled', 'expired')",
            name=op.f("ck_friend_requests_status"),
        ),
        sa.ForeignKeyConstraint(
            ["from_user_id"],
            ["users.id"],
            name=op.f("fk_friend_requests_from_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["to_user_id"],
            ["users.id"],
            name=op.f("fk_friend_requests_to_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_friend_requests")),
    )
    op.create_index("ix_friend_requests_to_status", "friend_requests", ["to_user_id", "status"])
    op.create_index("ix_friend_requests_from_status", "friend_requests", ["from_user_id", "status"])
    op.create_index(
        "uq_friend_requests_pending",
        "friend_requests",
        ["from_user_id", "to_user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    for table, first, second, check in (
        ("friendships", "user_a_id", "user_b_id", "ordered_users"),
        ("user_blocks", "blocker_id", "blocked_id", "different_users"),
    ):
        op.create_table(
            table,
            sa.Column(first, sa.Uuid(), nullable=False),
            sa.Column(second, sa.Uuid(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.CheckConstraint(
                f"{first} {'<' if table == 'friendships' else '<>'} {second}",
                name=op.f(f"ck_{table}_{check}"),
            ),
            sa.ForeignKeyConstraint(
                [first], ["users.id"], name=op.f(f"fk_{table}_{first}_users"), ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                [second], ["users.id"], name=op.f(f"fk_{table}_{second}_users"), ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint(first, second, name=op.f(f"pk_{table}")),
        )
        op.create_index(f"ix_{table}_{second}", table, [second])
    if app_role := os.getenv("POSTGRES_APP_USER"):
        role = (
            op.get_context()
            .dialect.identifier_preparer.quote_identifier(app_role)
            .replace("%", "%%")
        )
        op.execute(
            sa.DDL(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE friend_requests, friendships, user_blocks TO {role}"
            )
        )


def downgrade() -> None:
    op.drop_table("user_blocks")
    op.drop_table("friendships")
    op.drop_table("friend_requests")
