from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (
        CheckConstraint("mode IN ('meeting', 'livestream')", name="mode"),
        CheckConstraint("status IN ('active', 'closed')", name="status"),
        CheckConstraint("is_private = (password_hash IS NOT NULL)", name="private_has_password"),
        CheckConstraint("(status = 'closed') = (closed_at IS NOT NULL)", name="closed_consistent"),
        CheckConstraint(
            "max_participants IS NULL OR max_participants BETWEEN 2 AND 50", name="max_participants"
        ),
        Index("ix_rooms_host_active", "host_id", postgresql_where=text("status = 'active'")),
        Index("ix_rooms_status_created_at", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    code: Mapped[str] = mapped_column(String(12), unique=True)
    name: Mapped[str | None] = mapped_column(String(100))
    host_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    mode: Mapped[str] = mapped_column(String(16), server_default="meeting")
    is_private: Mapped[bool] = mapped_column(server_default=text("false"))
    password_hash: Mapped[str | None] = mapped_column(Text)
    max_participants: Mapped[int | None] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(String(16), server_default="active")
    closed_reason: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
