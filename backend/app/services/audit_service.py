from dataclasses import dataclass
from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


@dataclass(frozen=True, slots=True)
class AuditActor:
    id: UUID
    email: str
    ip: IPv4Address | IPv6Address | None


def record_audit(
    db: AsyncSession,
    actor: AuditActor,
    action: str,
    target_type: str,
    target_id: str | None = None,
    *,
    detail: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_id=actor.id,
            actor_label=actor.email,
            ip=actor.ip,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail or {},
        )
    )


async def list_audit(
    db: AsyncSession,
    *,
    actor: str | None,
    action: str | None,
    target_type: str | None,
    start: datetime | None,
    end: datetime | None,
    page: int,
    page_size: int,
) -> tuple[list[AuditLog], int]:
    query = select(AuditLog)
    if actor:
        try:
            actor_id = UUID(actor)
        except ValueError:
            query = query.where(func.lower(AuditLog.actor_label) == actor.lower())
        else:
            query = query.where(AuditLog.actor_id == actor_id)
    if action:
        query = query.where(AuditLog.action == action)
    if target_type:
        query = query.where(AuditLog.target_type == target_type)
    if start is not None:
        query = query.where(AuditLog.created_at >= start)
    if end is not None:
        query = query.where(AuditLog.created_at <= end)

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = await db.scalars(
        query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(rows), total or 0
