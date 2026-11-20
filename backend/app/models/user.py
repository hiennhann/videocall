from datetime import date, datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'admin')", name="role"),
        CheckConstraint("birth_date >= DATE '1900-01-01'", name="birth_date"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    email: Mapped[str] = mapped_column(String(254))
    password_hash: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(String(50))
    birth_date: Mapped[date | None] = mapped_column(Date)
    avatar_key: Mapped[str | None] = mapped_column(String(80))
    avatar_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discoverable_by_email: Mapped[bool] = mapped_column(server_default=text("true"))
    show_online_status: Mapped[bool] = mapped_column(server_default=text("true"))
    role: Mapped[str] = mapped_column(String(16), server_default="user", index=True)
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    must_change_password: Mapped[bool] = mapped_column(server_default=text("false"))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


Index("uq_users_email_lower", func.lower(User.email), unique=True)
