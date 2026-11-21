from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CallParticipant(Base):
    __tablename__ = "call_participants"
    __table_args__ = (
        Index(
            "ix_call_participants_user_joined",
            "user_id",
            text("joined_at DESC"),
            postgresql_where=text("user_id IS NOT NULL"),
        ),
        Index("ix_call_participants_room_joined", "room_id", "joined_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    room_id: Mapped[UUID] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"))
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    display_name: Mapped[str] = mapped_column(String(50))
    is_guest: Mapped[bool]
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    leave_reason: Mapped[str | None] = mapped_column(String(16))
