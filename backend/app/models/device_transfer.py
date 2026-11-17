from datetime import datetime
from uuid import UUID

from sqlalchemy import CHAR, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DeviceTransfer(Base):
    __tablename__ = "device_transfers"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    token_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
    expected_family: Mapped[UUID]
    use_cookie: Mapped[bool]
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
