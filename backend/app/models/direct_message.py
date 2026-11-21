from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint("user_a_id < user_b_id", name="ordered_users"),
        UniqueConstraint("user_a_id", "user_b_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    user_a_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    user_b_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    last_message_id: Mapped[int | None] = mapped_column(BigInteger)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    a_last_read_id: Mapped[int] = mapped_column(BigInteger, server_default="0")
    b_last_read_id: Mapped[int] = mapped_column(BigInteger, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DirectMessage(Base):
    __tablename__ = "direct_messages"
    __table_args__ = (
        CheckConstraint(
            "deleted_at IS NOT NULL OR char_length(content) BETWEEN 1 AND 2000",
            name="content_length",
        ),
        UniqueConstraint(
            "conversation_id", "sender_id", "client_msg_id", name="uq_direct_messages_client"
        ),
        Index("ix_direct_messages_conversation_id_id", "conversation_id", text("id DESC")),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    sender_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    client_msg_id: Mapped[UUID]
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
