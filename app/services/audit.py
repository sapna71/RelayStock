import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User


def record(session: AsyncSession, *, org_id: uuid.UUID, actor: User | None, action: str,
           entity_type: str, entity_id: uuid.UUID | None = None, detail: dict | None = None,
           ip: str | None = None) -> None:
    """Queue an audit row in the caller's transaction, so the log and the change commit together."""
    session.add(AuditLog(
        organization_id=org_id, actor_user_id=actor.id if actor else None,
        actor_email=actor.email if actor else None, action=action, entity_type=entity_type,
        entity_id=entity_id, detail=detail or {}, ip=ip,
    ))


async def list_logs(session: AsyncSession, org_id: uuid.UUID, *, action_prefix: str | None,
                    actor_id: uuid.UUID | None, limit: int, offset: int) -> dict:
    q = select(AuditLog).where(AuditLog.organization_id == org_id)
    if action_prefix:
        q = q.where(AuditLog.action.startswith(action_prefix, autoescape=True))
    if actor_id:
        q = q.where(AuditLog.actor_user_id == actor_id)
    total = (await session.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    items = (await session.execute(
        q.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).offset(offset))).scalars().all()
    return {"items": items, "total": total, "limit": limit, "offset": offset}